import os, re
import ffmpeg

def get_file_list(target_dir):
  # get the list of files in the current and subdirectories
  return [os.path.join(root, file) for root, _, files in os.walk(target_dir) for file in files if not re.search(r"_modified\.\w+", file)]

def get_file_info(file):
  print(f"Getting information for {file}")
  try:
    size = os.path.getsize(file)
    bitrate = ffmpeg.probe(file)["streams"][0]["bit_rate"]
    return {
      "size": size,
      "bitrate": bitrate
    }
  except Exception as e:
    print(f"Error getting file info for {file}: {e}")

def encode_video(file, bitrate, multiplier):
  output_file = file.replace(".", "_modified.")
  target_bitrate = int(int(bitrate) * multiplier)
  ffmpeg.input(file).output(output_file, vcodec='hevc_amf', crf=25, b=target_bitrate, loglevel='quiet').global_args('-hwaccel', 'auto').run()
  return output_file

def compare_files(file1, file2, delete_original):
  file1_size = os.path.getsize(file1) / 1024 / 1024
  file2_size = os.path.getsize(file2) / 1024 / 1024

  print(f"{file1} size: {round(file1_size, 2)}MB")
  print(f"{file2} size: {round(file2_size, 2)}MB")
  print(f"File size difference: {round((file2_size - file1_size), 2)}MB ({round((file2_size / file1_size * 100), 2)}%)")

  if delete_original.lower() == "y":
    os.remove(file1)
    print(f"{file1} deleted")
  return file2_size

def remove_failed_files(failed_files):
  for file in failed_files:
    # remove the failed encoding
    print(f"Removing {file.replace(".", "_modified.")} (failed to encode)")
    os.remove(file.replace(".", "_modified."))

def main():
  total_size_original = 0
  total_size_modified = 0

  target_dir = input("Enter the target directory: ")
  try:
    target_bitrate_multiplier = float(input("Enter the target bitrate multiplier (0.1 - 10, default 0.75): ") or 0.75)
  except ValueError:
    target_bitrate_multiplier = 0.75

  delete_original = input("Delete original files? (y/n default n): ").lower() or "n"

  file_list = get_file_list(target_dir)
  file_info = {file: get_file_info(file) for file in file_list}

  failed_to_encode = []

  total_files = len(file_info)
  for index, file in enumerate(file_info, start=1):
    try:
      output_file = encode_video(file, file_info[file]["bitrate"], target_bitrate_multiplier)
      modified_file_size = compare_files(file, output_file, delete_original)

      total_size_original += file_info[file]["size"] / 1024 / 1024
      total_size_modified += modified_file_size
    except Exception as e:
      print(f"Error: {e}")
      failed_to_encode.append(file)
      continue
    print(f"Processed {index}/{total_files} files ({round((index / total_files) * 100, 2)}%)")

  print("Encoding complete")
  print(f"Total original file size: {round(total_size_original, 2)}MB")
  print(f"Total modified file size: {round(total_size_modified, 2)}MB")
  if total_size_modified > 0:
    print(f"Total size difference: {round((total_size_modified - total_size_original), 2)}MB ({round((total_size_modified / total_size_original * 100), 2)}%)")

  if failed_to_encode:
    print(f"Failed to encode {len(failed_to_encode)} files:")
    try:
      remove_failed_files(failed_to_encode)
    except Exception as e:
      print(f"Error removing failed files: {e}")

if __name__ == "__main__":
  main()
