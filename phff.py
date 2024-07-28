import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, simpledialog, Tk

import cv2
import numpy as np
from PIL import Image

from _desmume import DeSmuME, Region

PARENT_DIRECTORY = Path(f'{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}')
skipped_starting_frame_saves = 0

SET_FLAG_FUNCTION_ADDR: dict[Region, int] = {
    Region.US: 0x209773C,
    Region.EU: 0x209779C,
}


@dataclass
class FlagSet:
    param0: int
    param1: int
    param2: int
    base_address: str  # str so we can store hex form
    offset_from_base: str  # str so we can store hex form
    flag_absolute_address: str  # str so we can store hex form
    flag_bit: str  # str so we can store hex form
    set: bool
    thumbnail: str
    video: str


def write_frames_to_video(frames: list[Image.Image], filename: Path) -> Path:
    video = cv2.VideoWriter(
        str(filename),
        cv2.VideoWriter.fourcc(*"avc1"),
        60,
        (256, 384),
    )
    for img in frames:
        video.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
    video.release()
    return filename


def get_filename_suffix() -> str:
    root = Tk()
    root.withdraw()
    suffix = simpledialog.askstring("Input", "Enter text for the filename suffix:", parent=root)
    root.destroy()
    if suffix:
        return suffix.replace(" ", "-")
    return "default"


def main() -> None:
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = filedialog.askopenfilename()

    emu = DeSmuME()
    emu.open(file_path)

    PARENT_DIRECTORY.mkdir()

    video_frames: list[Image.Image] = []

    def set_flag_breakpoint(frames: list[Image.Image]) -> None:
        global skipped_starting_frame_saves
        if skipped_starting_frame_saves > 13:
            emu.pause()
            suffix = get_filename_suffix()
            if not suffix == "default":
                # Get string timestamp to use in filenames
                timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                filename = f"{timestamp}-{suffix}"
                # Generate video
                video_file = str(write_frames_to_video(frames, PARENT_DIRECTORY / f"{filename}.mp4"))
                # Generate screenshot
                screenshot_file = str(PARENT_DIRECTORY / f"{filename}.png")
                emu.screenshot().save(screenshot_file)
                # Create save state
                emu.savestate.save_file(str(PARENT_DIRECTORY / f"{filename}.dsv"))

                # Get the function arguments for the set flag function
                r0 = emu.memory.register_arm9.r0
                r1 = emu.memory.register_arm9.r1
                r2 = emu.memory.register_arm9.r2

                # r0 contains the "base address" of the flags in memory
                base_address = r0
                # Calculate the offset from the base address that the flag is located at
                flag_offset_from_base = (r1 >> 5) * 4
                # Figure out what bit the flag is at
                flag_bit = 1 << (r1 & 0x1F)

                # The game code gives these values in terms of words (i.e. 4 bytes),
                # so to get it in terms of bytes, we need to do some conversion here
                while flag_bit > 0x80:
                    flag_bit >>= 8
                    flag_offset_from_base += 1

                flag_absolute_address = base_address + flag_offset_from_base

                # r2 is a boolean, which determines whether the flag should be set or unset
                set = bool(r2)

                (PARENT_DIRECTORY / f"{filename}.json").write_text(
                    json.dumps(
                        asdict(
                            FlagSet(
                                param0=r0,
                                param1=r1,
                                param2=r2,
                                base_address=hex(r0),
                                offset_from_base=hex(flag_offset_from_base),
                                flag_absolute_address=hex(flag_absolute_address),
                                flag_bit=hex(flag_bit),
                                set=set,
                                thumbnail=screenshot_file,
                                video=video_file,
                            )
                        ),
                        indent=2,
                    )
                )
            emu.resume()
        else:
            print(skipped_starting_frame_saves)
            skipped_starting_frame_saves += 1

    # Register a breakpoint at the beginning of the set flag function
    # that calls the callback defined above
    emu.memory.register_exec(
        SET_FLAG_FUNCTION_ADDR[emu.rom_region],
        lambda addr, size: set_flag_breakpoint(video_frames),
    )

    while not emu.has_quit:
        # Save current video frame and discard old ones
        video_frames.append(emu.screenshot())
        if len(video_frames) > 600:
            video_frames = video_frames[1:]

        emu.cycle()


if __name__ == "__main__":
    main()
