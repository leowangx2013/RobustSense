import os
import torch
import logging
import torch.optim as optim
import numpy as np

from tqdm import tqdm

# train utils
from train_utils.eval_functions import val_and_logging

# utils
from general_utils.time_utils import time_sync


def pretrain_classifier(
    args,
    classifier,
    # miss_simulator,
    train_dataloader,
    val_dataloader,
    test_dataloader,
    classifier_loss_func,
    tb_writer,
    num_batches,
):
    """The pretraining function for tbe backbone network."""
    # define the miss handler and miss detector
    # miss_handler = miss_simulator.miss_handler
    # miss_detector = miss_simulator.miss_detector
    # miss_generator = miss_simulator.miss_generator

    # model config
    classifier_config = args.dataset_config[args.model]

    # Init the optimizer
    lr = args.lr if args.lr is not None else classifier_config["start_lr"]
    optimizer = optim.Adam(classifier.parameters(), lr=lr)
    if args.verbose:
        for name, param in classifier.named_parameters():
            if param.requires_grad:
                logging.info(name)

    # define learning rate scheduler
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer,
        step_size=classifier_config["scheduler_step"],
        gamma=classifier_config["scheduler_gamma"],
    )

    # Training loop
    logging.info("---------------------------Start Pretraining Classifier-------------------------------")
    start = time_sync()
    best_val_acc = 0
    best_classifier_weight = os.path.join(args.weight_folder, f"{args.dataset}_{args.model}_pretrain_best.pt")
    latest_classifier_weight = os.path.join(args.weight_folder, f"{args.dataset}_{args.model}_pretrain_latest.pt")

    for epoch in range(classifier_config["train_epochs"]):

        # set model to train mode
        classifier.train()
        # miss_handler.eval()
        # miss_detector.eval()
        # miss_generator.eval()
        
        # training loop
        train_loss_list = []
        for i, (data, labels) in tqdm(enumerate(train_dataloader), total=num_batches):
            # send data label to device (data is sent in the model)
            labels = labels.to(args.device)
            logits = classifier(data)
            # print("logits: ", type(logits))
            # print("labels: ", type(labels))
            loss = classifier_loss_func(logits, labels)

            # back propagation
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss_list.append(loss.item())

            # Write train log
            if i % 200 == 0:
                tb_writer.add_scalar("Train/Train loss", loss.item(), epoch * num_batches + i)

        # validation and logging
        train_loss = np.mean(train_loss_list)
        val_acc = val_and_logging(
            args,
            epoch,
            tb_writer,
            classifier,
            val_dataloader,
            test_dataloader,
            classifier_loss_func,
            (train_loss, 0),
        )

        # Save the latest model
        torch.save(classifier.state_dict(), latest_classifier_weight)

        # Save the best model according to validation result
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(classifier.state_dict(), best_classifier_weight)

        # Update the learning rate scheduler
        scheduler.step()

    # flush and close the TB writer
    tb_writer.flush()
    tb_writer.close()

    end = time_sync()
    logging.info("------------------------------------------------------------------------")
    logging.info(f"Total processing time: {(end - start): .3f} s")
