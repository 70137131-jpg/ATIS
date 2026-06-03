import os
import shutil


def discover_classes(source_dir, splits):
    """Find class folders present in the source dataset splits."""
    classes = set()
    for split in splits:
        split_path = os.path.join(source_dir, split)
        if not os.path.isdir(split_path):
            continue
        for name in os.listdir(split_path):
            class_path = os.path.join(split_path, name)
            if os.path.isdir(class_path):
                classes.add(name)
    return sorted(classes)


def format_atis_dataset(source_dir, dest_dir):
    """
    Reformats the ATIS dataset structure for Ultralytics YOLO Classification.
    """
    folder_mapping = {
        'testing_data': 'val',
        'training_data': 'train'
    }
    
    classes = discover_classes(source_dir, folder_mapping.keys())
    if not classes:
        raise SystemExit(f"No class folders found under {source_dir}")
    
    os.makedirs(dest_dir, exist_ok=True)
    
    for old_split, new_split in folder_mapping.items():
        for cls in classes:
            src_path = os.path.join(source_dir, old_split, cls)
            dest_path = os.path.join(dest_dir, new_split, cls)
            
            # Copy the directory tree
            if os.path.exists(src_path):
                print(f"Copying {src_path} -> {dest_path}")
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                print(f"Warning: Source path {src_path} not found.")

if __name__ == "__main__":
    SOURCE_DIRECTORY = "Tire Textures" 
    DESTINATION_DIRECTORY = "ATIS_Dataset"
    
    format_atis_dataset(SOURCE_DIRECTORY, DESTINATION_DIRECTORY)
    print("Dataset restructuring complete. Ready for YOLO training.")
