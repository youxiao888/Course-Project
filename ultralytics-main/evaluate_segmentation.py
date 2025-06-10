import os
from ultralytics import YOLO
import numpy as np
from pathlib import Path
import cv2

def calculate_iou(pred_mask, gt_mask):

    intersection = np.logical_and(pred_mask, gt_mask).sum()
    union = np.logical_or(pred_mask, gt_mask).sum()
    if union == 0:
        return 0
    return intersection / union

def load_label_mask(label_path, img_shape):

    if not os.path.exists(label_path):
        return np.zeros(img_shape[:2], dtype=bool)
    
    # 使用uint8类型而不是bool类型
    mask = np.zeros(img_shape[:2], dtype=np.uint8)
    
    try:
        with open(label_path, 'r') as f:
            lines = f.readlines()
            
        for line in lines:
            # YOLO格式：class x1 y1 x2 y2 ...
            values = list(map(float, line.strip().split()))
            points = np.array(values[1:]).reshape(-1, 2)
            points[:, 0] *= img_shape[1]  # 将x坐标还原
            points[:, 1] *= img_shape[0]  # 将y坐标还原
            points = points.astype(np.int32)
            
            # 填充多边形，使用255作为填充值
            cv2.fillPoly(mask, [points], 255)
            
    except Exception as e:
        print(f"Error loading label file {label_path}: {e}")
        
    # 返回时转换为bool类型
    return mask > 0

def main():
    # 设置路径
    model_path = "runs/segment/train6/weights/best.pt"
    images_dir = "data/valid/images"
    labels_dir = "data/valid/labels"
    
    # 加载模型
    model = YOLO(model_path)
    
    # 存储所有图片的IoU
    all_ious = []
    
    # 遍历验证集图片
    for img_file in os.listdir(images_dir):
        if not img_file.endswith(('.jpg', '.jpeg', '.png')):
            continue
            
        img_path = os.path.join(images_dir, img_file)
        label_file = os.path.splitext(img_file)[0] + '.txt'
        label_path = os.path.join(labels_dir, label_file)
        
        # 读取图片
        img = cv2.imread(img_path)
        if img is None:
            print(f"Could not read image: {img_path}")
            continue
            
        # 获取模型预测
        results = model(img_path)[0]
        pred_masks = results.masks
        
        if pred_masks is None:
            print(f"No predictions for image: {img_path}")
            continue
            
        # 获取真实标签掩码
        gt_mask = load_label_mask(label_path, img.shape)
        
        # 合并所有预测掩码
        combined_pred_mask = np.zeros(img.shape[:2], dtype=bool)
        for mask_data in pred_masks.data:
            mask = mask_data.cpu().numpy()
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]))
            combined_pred_mask = np.logical_or(combined_pred_mask, mask > 0.5)
        
        # 计算IoU
        iou = calculate_iou(combined_pred_mask, gt_mask)
        all_ious.append(iou)
        print(f"Image: {img_file}, IoU: {iou:.4f}")
    
    # 计算平均IoU
    mean_iou = np.mean(all_ious)
    print(f"\nMean IoU across all images: {mean_iou:.4f}")
    print(f"Number of images evaluated: {len(all_ious)}")

if __name__ == "__main__":
    main() 