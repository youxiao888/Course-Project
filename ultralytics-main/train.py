from ultralytics import YOLO
 
if __name__ == '__main__':

    model = YOLO(r'ultralytics/cfg/models/11/yolo11-seg.yaml')  
    model.train(data=r'data.yaml',
                imgsz=640,
                epochs=1000,
                single_cls=True,  
                batch=16,            
                )

