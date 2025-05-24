import exiftool
import os

def get_all_metadata(file_path):
    """
    Extract all available metadata from a file using ExifTool and return it as a formatted string.
    """
    try:
        # Ensure absolute path
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
        
        # Initialize the string that will collect all metadata in a human-readable format
        metadata_string = "ExifTool Metadata:\n"

        with exiftool.ExifToolHelper() as et:
            # Extract all metadata
            metadata = et.get_metadata(file_path)[0]  # Returns a dict for the first file

        if not metadata:
            metadata_string += "  (No metadata found)\n"
            return metadata_string.strip()

        # Define tags to exclude (directories and dates)
        exclude_patterns = [
            # Directory-related tags
            'File:Directory',
            'File:FileName',
            'SourceFile',
            # Date-related tags
            'File:FileModifyDate',
            'File:FileAccessDate',
            'File:FileCreateDate',
            'EXIF:CreateDate',
            'EXIF:ModifyDate',
            'EXIF:DateTimeOriginal',
            'XMP:CreateDate',
            'XMP:ModifyDate',
            'XMP:DateCreated',
            'IPTC:DateCreated',
            'IPTC:TimeCreated',
            'File:FileInodeChangeDate',
            ':Date',
            ':Time'
        ]

        # Format metadata into string, excluding unwanted tags
        metadata_string += "ExifTool Metadata (Excluding Directories and Dates):\n"
        filtered_metadata = []
        for key, value in sorted(metadata.items()):
            # Skip if value is empty or None
            if value is None or not str(value).strip():
                continue
            # Skip if key matches any exclude pattern
            if any(pattern.lower() in key.lower() for pattern in exclude_patterns):
                continue
            filtered_metadata.append(f"  {key}: {value}")

        if filtered_metadata:
            metadata_string += "\n".join(filtered_metadata)
        else:
            metadata_string += "  (No metadata found after filtering directories and dates)"

        return metadata_string.strip()


    except exiftool.exceptions.ExifToolExecuteError as e:
        return f"Error: ExifTool failed to execute. Ensure ExifTool is installed and in PATH.\nDetails: {str(e)}"
    except Exception as e:
        return f"Error extracting metadata for '{file_path}': {str(e)}"

# Example usage
if __name__ == "__main__":
    file_path = "/home/suz/work/dfexpert/demo_agent/test/Attached/0014950_Carved.png"  # Replace with your file path
    metadata = get_all_metadata(file_path)
    print(metadata)
