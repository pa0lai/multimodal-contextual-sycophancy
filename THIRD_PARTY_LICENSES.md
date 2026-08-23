# Third-party datasets and terms

## WHOOPS! abnormal split

The 499-case abnormal split is derived from WHOOPS! (Bitton et al., 2023).

- Dataset: https://huggingface.co/datasets/nlphuji/whoops
- Analysis dataset: https://huggingface.co/datasets/nlphuji/whoops-analysis
- Official agreement: https://whoops-benchmark.github.io/static/pdfs/whoops_license_agreement.txt
- Paper: https://arxiv.org/abs/2303.07274

The official additional agreement is reproduced verbatim:

> **WHOOPS! Dataset License Agreement**
>
> The WHOOPS! Dataset is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Alongside this license, the following conditions apply:
>
> 1. **Purpose:** The dataset was primarily designed for use as a test set.
>
> 2. **Commercial Use:** Commercially, the dataset may be used as a test set, but it's prohibited to use it as a training set.
>
> 3. **Rights on Images:** All rights to the images within the dataset are retained by the WHOOPS! authors.
>
> By accessing or using this dataset, you acknowledge and agree to abide by these terms in conjunction with the CC BY 4.0 license.

WHOOPS! image bytes are not included in the code repository. A separate local image archive was not created because only 466/499 evaluated images currently have exact decoded-pixel matches to pinned official artifacts.

## ImageNet-1k normal control

The 500-image normal selection originates from the `ILSVRC/imagenet-1k` training split on Hugging Face. ImageNet images are not covered by this repository's MIT or CC BY 4.0 licenses. Users must accept and comply with the ImageNet and Hugging Face dataset terms and obtain the images themselves.

ImageNet image bytes must not be placed in the Git repository, a GitHub Release, a project Google Drive archive, or any other public release artifact.

