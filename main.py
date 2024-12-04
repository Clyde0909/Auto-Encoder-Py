import os, re
import ffmpeg

def get_file_list(target_dir):
  # get the list of files in the current and subdirectories
  file_list = []
  for root, dirs, files in os.walk(target_dir):
    for file in files:
      # if file name ends with _modified, skip it( regex can be used here)
      if re.search(r"_modified\.\w+", file):
        continue
      else:
        file_list.append(os.path.join(root, file))
  return file_list

def get_file_info(file): # file path is windows style
  print(f"Getting information for {file}")

  file_info_dict = {}
  # get the file size in bytes
  file_info_dict["size"] = os.path.getsize(file)
  # get the video bitrate
  file_info_dict["bitrate"] = ffmpeg.probe(file)["streams"][0]["bit_rate"]
  
  # return the file information as a dictionary
  return file_info_dict

def encode_video(file, bitrate):
  # make output file name
  output_file = file.replace(".", "_modified.")
  target_bitrate = int(int(bitrate) * 0.75)
  # encode the video into h265 format with ffmpeg, use hardware acceleration, disable ffmpeg logging
  ffmpeg\
    .input(file)\
    .output(output_file, vcodec='hevc_amf', crf=25, b=target_bitrate, loglevel='quiet')\
    .global_args('-hwaccel', 'auto')\
    .run()
  
  # if the file is encoded, return the new file name
  return output_file
  
def compare_files(file1, file2, delete_original):
  # get the file size for each file(in MB)
  file1_size = os.path.getsize(file1)/1024/1024
  file2_size = os.path.getsize(file2)/1024/1024

  # compare the file sizes
  print(f"{file1} size: {round(file1_size, 2)}MB")
  print(f"{file2} size: {round(file2_size, 2)}MB")
  print(f"File size difference: {round((file2_size - file1_size), 2)}MB")

  # delete the original file
  if delete_original == "y":
    os.remove(file1)
    print(f"{file1} deleted")
    return file2_size
  else:
    return file2_size

def main():
  total_size_original = 0
  total_size_modified = 0

  # get input from the user to define the target directory
  target_dir = input("Enter the target directory: ")
  # get input from the user to define the target bitrate multiplier (float, 0.1 - 10, default 0.75)
  try:
    target_bitrate_multiplier = float(input("Enter the target bitrate multiplier (0.1 - 10, default 0.75): "))
  except ValueError:
    target_bitrate_multiplier = 0.75
  # get input from the user to whether to delete the original files (y/n, default n)
  try:
    delete_original = input("Delete original files? (y/n default n): ")
  except ValueError:
    delete_original = "n"

  # get the list of files in the target directory
  file_list = get_file_list(target_dir)
  # get the file information for each file in the list
  file_info = {file: get_file_info(file) for file in file_list}
  
  # encode the video files
  for file in file_info:
    output_file = encode_video(file, file_info[file]["bitrate"])
    modified_file_size = compare_files(file, output_file, delete_original)

    total_size_original += file_info[file]["size"]/1024/1024
    total_size_modified += modified_file_size
  
  print("Encoding complete")
  print(f"Total original file size: {round(total_size_original, 2)}MB")
  print(f"Total modified file size: {round(total_size_modified, 2)}MB")
  print(f"Total size difference: {round((total_size_modified - total_size_original), 2)}MB")

if __name__ == "__main__":
  main()


