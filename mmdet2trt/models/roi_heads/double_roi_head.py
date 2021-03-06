from mmdet2trt.models.builder import register_warper, build_warper
import torch
from torch import nn
import torch.nn.functional as F
from mmdet.core.bbox.coder.delta_xywh_bbox_coder import delta2bbox
from mmdet2trt.core.post_processing.batched_nms import BatchedNMS
from .standard_roi_head import StandardRoIHeadWarper

@register_warper("mmdet.models.roi_heads.double_roi_head.DoubleHeadRoIHead")
class DoubleHeadRoIHeadWarper(StandardRoIHeadWarper):
    def __init__(self, module):
        super(DoubleHeadRoIHeadWarper, self).__init__(module)

        self.reg_roi_scale_factor = self.module.reg_roi_scale_factor
        

    def forward(self, feat ,proposals):
        zeros = proposals.new_zeros([proposals.shape[0], 1])
        rois = torch.cat([zeros, proposals], dim=1)

        bbox_cls_feats = self.bbox_roi_extractor(
            feat[:self.bbox_roi_extractor.num_inputs], rois)
        bbox_reg_feats = self.bbox_roi_extractor(
            feat[:self.bbox_roi_extractor.num_inputs], rois,
            roi_scale_factor=self.reg_roi_scale_factor)
        if self.shared_head is not None:
            bbox_cls_feats = self.shared_head(bbox_cls_feats)
            bbox_reg_feats = self.shared_head(bbox_reg_feats)

        # rcnn
        cls_score, bbox_pred = self.bbox_head(bbox_cls_feats, bbox_reg_feats)

        if isinstance(cls_score, list):
            cls_score = sum(cls_score) / float(len(cls_score))
        scores = F.softmax(cls_score, dim=1)
        bboxes = delta2bbox(proposals, bbox_pred, self.bbox_head.bbox_coder.means,
                    self.bbox_head.bbox_coder.stds)

        num_bboxes = bboxes.shape[0]
        scores = scores.unsqueeze(0)
        bboxes = bboxes.view(1, num_bboxes, -1, 4)
        bboxes_ext = bboxes.new_zeros((1,num_bboxes, 1, 4))
        bboxes = torch.cat([bboxes, bboxes_ext], 2)
        num_detections, det_boxes, det_scores, det_classes = self.rcnn_nms(scores, bboxes, num_bboxes, self.test_cfg.max_per_img)

        return num_detections, det_boxes, det_scores, det_classes
