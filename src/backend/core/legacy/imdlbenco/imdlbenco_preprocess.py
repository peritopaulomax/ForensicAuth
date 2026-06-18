"""Single-image preprocessing using IMDLBenCo transforms."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image

from core.legacy.imdlbenco.imdlbenco_catalog import ImdlBencoMethod


@dataclass
class PreprocessedBatch:
    image: torch.Tensor
    mask: torch.Tensor
    edge_mask: torch.Tensor | None
    label: torch.Tensor
    origin_shape: tuple[int, int]
    content_shape: tuple[int, int]
    original_rgb: np.ndarray
    is_padding: bool
    is_resizing: bool
    dct_coef: torch.Tensor | None = None
    qtables: torch.Tensor | None = None


def preprocess_single_image(evidence_path: str, spec: ImdlBencoMethod) -> PreprocessedBatch:
    from IMDLBenCo.transforms import EdgeMaskGenerator, get_albu_transforms

    img = Image.open(evidence_path).convert("RGB")
    tp_img = np.array(img)
    origin_h, origin_w = tp_img.shape[:2]
    gt_img = np.zeros((origin_h, origin_w, 3), dtype=np.uint8)

    gt_bin = (np.mean(gt_img, axis=2, keepdims=True) > 127.5) * 1.0
    gt_bin = gt_bin.transpose(2, 0, 1)[0]
    masks_list = [gt_bin]

    edge_mask_tensor = None
    if spec.edge_width:
        edge_gen = EdgeMaskGenerator(spec.edge_width)
        gt_edge = edge_gen(gt_bin)[0][0]
        masks_list.append(gt_edge)

    output_size = (spec.image_size, spec.image_size)
    if spec.use_padding:
        post_transform = get_albu_transforms(type_="pad", output_size=output_size)
    else:
        post_transform = get_albu_transforms(type_="resize", output_size=output_size)

    res = post_transform(image=tp_img, masks=masks_list)
    tensor_img = res["image"]
    gt_mask = res["masks"][0].unsqueeze(0).float()

    if spec.edge_width:
        edge_mask_tensor = res["masks"][1].unsqueeze(0).float()
    else:
        edge_mask_tensor = gt_mask.clone()

    content_shape = (origin_h, origin_w)
    if spec.use_resizing:
        content_shape = output_size

    batch = PreprocessedBatch(
        image=tensor_img,
        mask=gt_mask,
        edge_mask=edge_mask_tensor,
        label=torch.tensor([0], dtype=torch.long),
        origin_shape=(origin_h, origin_w),
        content_shape=content_shape,
        original_rgb=tp_img,
        is_padding=spec.use_padding,
        is_resizing=spec.use_resizing,
    )

    if spec.id == "cat_net":
        _attach_cat_net_jpeg_features(batch)

    return batch


def _attach_cat_net_jpeg_features(batch: PreprocessedBatch) -> None:
    from IMDLBenCo.model_zoo.cat_net.cat_net_post_function import cat_net_post_func

    data = {"image": batch.image}
    cat_net_post_func(data)
    batch.dct_coef = torch.tensor(data["DCT_coef"], dtype=torch.float32).unsqueeze(0)
    batch.qtables = torch.tensor(data["qtables"], dtype=torch.float32).unsqueeze(0)


def postprocess_mask(
    pred_mask: np.ndarray,
    batch: PreprocessedBatch,
) -> np.ndarray:
    import cv2

    heatmap = np.clip(pred_mask.astype(np.float32), 0.0, 1.0)
    oh, ow = batch.origin_shape

    if batch.is_padding:
        ch, cw = batch.content_shape
        heatmap = heatmap[:ch, :cw]

    if heatmap.shape[:2] != (oh, ow):
        heatmap = cv2.resize(heatmap, (ow, oh), interpolation=cv2.INTER_LINEAR)

    return heatmap
