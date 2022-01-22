# Learning to Predict Trustworthiness with Steep Slope Loss

This project is based on [ConfidNet
](https://github.com/valeoai/ConfidNet). The code is tested with Python 3.8.5 and PyTorch 1.6.0/1.7.1 under Ubuntu 1804 equipped with Nvidia GTX 1080 ti graphics cards. More details can be found in our [paper](https://arxiv.org/abs/2110.00054).

If you find this code useful for your research, please cite the following papers:

```
@incollection{NIPS2019_8556,
   title = {Addressing Failure Prediction by Learning Model Confidence},
   author = {Corbi\`{e}re, Charles and THOME, Nicolas and Bar-Hen, Avner and Cord, Matthieu and P\'{e}rez, Patrick},
   booktitle = {Advances in Neural Information Processing Systems 32},
   editor = {H. Wallach and H. Larochelle and A. Beygelzimer and F. d\textquotesingle Alch\'{e}-Buc and E. Fox and R. Garnett},
   pages = {2902--2913},
   year = {2019},
   publisher = {Curran Associates, Inc.},
   url = {http://papers.nips.cc/paper/8556-addressing-failure-prediction-by-learning-model-confidence.pdf}
}

@inproceedings{Luo_NeurIPS_2021,
  title={Learning to Predict Trustworthiness with Steep Slope Loss},
  author={Luo, Yan and Wong, Yongkang and Kankanhalli, Mohan and Zhao, Qi},
  booktitle={Advances in Neural Information Processing Systems},
  year={2021}
```

## Installation
1. Clone the repo.

2. Install this repository and the dependencies using pip.

3. Configure the root folder in the file *predict_trustworthiness_smallscale/confidnet/train.py*, e.g.,
```
import sys
sys.path.append('/home/yluo/project/python/oracle_learning/predict_trustworthiness_smallscale')
```


## Datasets

MNIST and CIFAR-10 datasets are managed by Pytorch dataloader. First time you run a script, the dataloader will download the dataset in ```predict_trustworthiness_smallscale/confidnet/data/DATASETNAME-data```.

Download the official pre-trained [ConfidNet](https://github.com/valeoai/ConfidNet/releases/tag/v0.1.0). Extract the pre-trained models to 
 ```
predict_trustworthiness_smallscale/confidnet/pretrained/mnist_pretrained/confidnet/
predict_trustworthiness_smallscale/confidnet/pretrained/cifar10_pretrained/confidnet/
```

## Running the code

Execute the following command for training: 
```bash
$ cd predict_trustworthiness_smallscale/confidnet
$ ./scripts/train.sh 
```

The resulting output files can be found in
```
experiments/mnist_steep/logs.csv
experiments/cifar10_steep/logs.csv
```


#### Pre-trained models
Fine-tuned models with the steep slope loss on MNIST and CIFAR-10 are available via this [link](https://drive.google.com/drive/folders/1I-oUDUV5pM5o3qtK6uBx8Nx872cKqAZF?usp=sharing). 

