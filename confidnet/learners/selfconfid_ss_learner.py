import os
from collections import OrderedDict

import numpy as np
import torch
from tqdm import tqdm

from confidnet.learners.learner import AbstractLeaner
from confidnet.utils import misc
from confidnet.utils.logger import get_logger
from confidnet.utils.metrics import Metrics

LOGGER = get_logger(__name__, level="DEBUG")

def calibrate_boundary(feats, gt_labels, num_steps=1000):
    db = 0.0
    max_acc = 0.0
    x_min, x_max = feats.min().item(), feats.max().item()
    steps = np.linspace(x_min, x_max, num_steps, endpoint=True)
    for x in steps:
        pred_labels = feats >= x
        # pred_labels = torch.logical_and(feat_tensor[:,0] >= (x_pos_mean-x), feat_tensor[:,0] <= (x_pos_mean+x))

        tp = pred_labels[gt_labels].sum().item()/gt_labels.sum().item()
        # tn = torch.logical_and(pred_labels==False,gt_labels==False).sum().item()/pred_labels.shape[0]
        tn = torch.logical_and(torch.logical_not(pred_labels),torch.logical_not(gt_labels)).sum().item()/torch.logical_not(gt_labels).sum().item()
        acc = tp+tn
        if acc >= max_acc:
            max_acc = acc
            db = x
    return db

class SelfConfidSteepLearner(AbstractLeaner):
    def __init__(self, config_args, train_loader, val_loader, test_loader, start_epoch, device):
        super().__init__(config_args, train_loader, val_loader, test_loader, start_epoch, device)
        self.freeze_layers()
        self.disable_bn(verbose=True)
        self.db = 0.0 #config_args['training']['loss']['db']
        if self.config_args["model"].get("uncertainty", None):
            self.disable_dropout(verbose=True)

    def train(self, epoch):
        self.model.train()
        self.model.module.pred_network.eval()
        self.disable_bn()
        if self.config_args["model"].get("uncertainty", None):
            self.disable_dropout()
        metrics = Metrics(
            self.metrics, self.prod_train_len, self.num_classes
        )
        loss, confid_loss = 0, 0
        len_steps, len_data = 0, 0

        all_oracle_pred = torch.empty(0).cuda()
        all_oracle_gt = torch.empty(0, dtype=torch.bool).cuda()

        # Training loop
        loop = tqdm(self.train_loader)
        for batch_id, (data, target) in enumerate(loop):
            data, target = data.to(self.device), target.to(self.device)
            self.optimizer.zero_grad()
            output = self.model(data)

            # Potential temperature scaling
            if self.temperature:
                output = list(output)
                output[0] = output[0] / self.temperature
                output = tuple(output)

            if self.task == "classification":
                current_loss = self.criterion(output, target)
            elif self.task == "segmentation":
                current_loss = self.criterion(output, target.squeeze(dim=1))
            current_loss.backward()
            loss += current_loss
            self.optimizer.step()
            if self.task == "classification":
                len_steps += len(data)
                len_data = len_steps
            elif self.task == "segmentation":
                len_steps += len(data) * np.prod(data.shape[-2:])
                len_data += len(data)

            # Update metrics
            pred = output[0].argmax(dim=1, keepdim=True)
            confidence = torch.sigmoid(output[1])
            
            metrics.update(pred, target, confidence)
            
            all_oracle_pred = torch.cat((all_oracle_pred, output[1].squeeze()), dim=0)
            all_oracle_gt = torch.cat((all_oracle_gt, (pred.squeeze() == target)), dim=0)

            # Update the average loss
            loop.set_description(f"Epoch {epoch}/{self.nb_epochs}")
            loop.set_postfix(
                OrderedDict(
                    {
                        "loss_confid": f"{(loss / len_data):05.3e}",
                        "acc": f"{(metrics.accuracy / len_steps):05.2%}",
                    }
                )
            )
            loop.update()

        # self.db = calibrate_boundary(all_oracle_pred, all_oracle_gt)

        # Eval on epoch end
        scores = metrics.get_scores(split="train")
        logs_dict = OrderedDict(
            {
                "epoch": {"value": epoch, "string": f"{epoch:03}"},
                "lr": {
                    "value": self.optimizer.param_groups[0]["lr"],
                    "string": f"{self.optimizer.param_groups[0]['lr']:05.1e}",
                },
                "train/loss_confid": {
                    "value": loss / len_data,
                    "string": f"{(loss / len_data):05.4e}",
                },
                "train/db": {
                    "value":  self.db,
                    "string": f"{self.db:.8f}",
                },
            }
        )
        for s in scores:
            logs_dict[s] = scores[s]

        # logs_dict['train/db'] = self.db

        # Val scores
        val_losses, scores_val = self.evaluate(self.val_loader, self.prod_val_len, split="val")
        logs_dict["val/loss_confid"] = {
            "value": val_losses["loss_confid"].item() / self.nsamples_val,
            "string": f"{(val_losses['loss_confid'].item() / self.nsamples_val):05.4e}",
        }
        for sv in scores_val:
            logs_dict[sv] = scores_val[sv]

        # Test scores
        test_losses, scores_test = self.evaluate(self.test_loader, self.prod_test_len, split="test")
        logs_dict["test/loss_confid"] = {
            "value": test_losses["loss_confid"].item() / self.nsamples_test,
            "string": f"{(test_losses['loss_confid'].item() / self.nsamples_test):05.4e}",
        }
        for st in scores_test:
            logs_dict[st] = scores_test[st]

        # Print metrics
        misc.print_dict(logs_dict)

        # Save the model checkpoint
        self.save_checkpoint(epoch)

        # CSV logging
        misc.csv_writter(path=self.output_folder / "logs.csv", dic=OrderedDict(logs_dict))

        # Tensorboard logging
        self.save_tb(logs_dict)

        # Scheduler step
        if self.scheduler:
            self.scheduler.step()

    def evaluate(self, dloader, len_dataset, split="test", verbose=False, npz_file='', **args):
        self.model.eval()
        metrics = Metrics(self.metrics, len_dataset, self.num_classes)
        loss = 0

        # Evaluation loop
        loop = tqdm(dloader, disable=not verbose)
        for batch_id, (data, target) in enumerate(loop):
            data, target = data.to(self.device), target.to(self.device)

            with torch.no_grad():
                output = self.model(data)
                if self.task == "classification":
                    loss += self.criterion(output, target)
                elif self.task == "segmentation":
                    loss += self.criterion(output, target.squeeze(dim=1))
                # Update metrics
                pred = output[0].argmax(dim=1, keepdim=True)
                confidence = torch.sigmoid(output[1]-self.db)
                metrics.update(pred, target, confidence)

        scores = metrics.get_scores(split=split, tn_th=0.5)
        if npz_file != '':
            metrics.save_to_npz(npz_file)
        losses = {"loss_confid": loss}
        return losses, scores

    def load_checkpoint(self, state_dict, uncertainty_state_dict=None, strict=True):
        if not uncertainty_state_dict:
            # self.model.load_state_dict(state_dict, strict=strict)
            load_pred_network = True
            for x in list(state_dict.keys()):
                if 'uncertainty' in x:
                    load_pred_network = False
                    break
            if load_pred_network:
                self.model.pred_network.load_state_dict(state_dict, strict=True)
                uncertainty_network_arch = self.model.uncertainty_network.state_dict()
                # 1. filter out unnecessary keys
                pretrained_dict = {k: v for k, v in state_dict.items() if (k in uncertainty_network_arch) and (uncertainty_network_arch[k].shape == state_dict[k].shape)}
                # 2. overwrite entries in the existing state dict
                self.model.uncertainty_network.state_dict().update(pretrained_dict) 
                # 3. load the new state dict
                self.model.uncertainty_network.load_state_dict(pretrained_dict, strict=False)
            else:
                self.model.load_state_dict(state_dict, strict=strict)

            # uncertainty_network_arch = self.model.uncertainty_network.state_dict()
            # # 1. filter out unnecessary keys
            # pretrained_dict = {k: v for k, v in state_dict.items() if k in uncertainty_network_arch}
            # # 2. overwrite entries in the existing state dict
            # self.model.uncertainty_network.state_dict().update(pretrained_dict) 
            # # 3. load the new state dict
            # self.model.uncertainty_network.load_state_dict(pretrained_dict)
        else:
            self.model.pred_network.load_state_dict(state_dict, strict=strict)
            # self.model.uncertainty_network.load_state_dict(uncertainty_state_dict, strict=False)

            # 1. filter out unnecessary keys
            if self.task == "classification":
                state_dict = {
                    k: v
                    for k, v in uncertainty_state_dict.items()
                    if k not in ["fc2.weight", "fc2.bias"]
                }
            if self.task == "segmentation":
                state_dict = {
                    k: v
                    for k, v in uncertainty_state_dict.items()
                    if k
                    not in [
                        "up1.conv2.cbr_unit.0.weight",
                        "up1.conv2.cbr_unit.0.bias",
                        "up1.conv2.cbr_unit.1.weight",
                        "up1.conv2.cbr_unit.1.bias",
                        "up1.conv2.cbr_unit.1.running_mean",
                        "up1.conv2.cbr_unit.1.running_var",
                    ]
                }
            # 2. overwrite entries in the existing state dict
            self.model.uncertainty_network.state_dict().update(state_dict)
            # 3. load the new state dict
            self.model.uncertainty_network.load_state_dict(state_dict, strict=False)

    def freeze_layers(self):
        # Eventual fine-tuning for self-confid
        LOGGER.info("Freezing every layer except uncertainty")
        for param in self.model.named_parameters():
            if "uncertainty" in param[0]:
            # if ("uncertainty" in param[0]) and ('uncertainty_network.uncertainty' not in param[0]):
            # if 'uncertainty_network.uncertainty' in param[0]:
                print(param[0], "kept to training")
                continue
            param[1].requires_grad = False

    def disable_bn(self, verbose=False):
        # Freeze also BN running average parameters
        if verbose:
            LOGGER.info("Keeping original BN parameters")
        for layer in self.model.named_modules():
            if "bn" in layer[0] or "cbr_unit.1" in layer[0]:
                if verbose:
                    print(layer[0], "original BN setting")
                layer[1].momentum = 0
                layer[1].eval()

    def disable_dropout(self, verbose=False):
        # Freeze also BN running average parameters
        if verbose:
            LOGGER.info("Disable dropout layers to reduce stochasticity")
        for layer in self.model.named_modules():
            if "dropout" in layer[0]:
                if verbose:
                    print(layer[0], "set to eval mode")
                layer[1].eval()
