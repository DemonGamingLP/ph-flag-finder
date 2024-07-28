from functools import cached_property
from tkinter import Button, Label, Tk
from enum import StrEnum
import keyboard
import pygame
import win32api
import win32gui
from desmume.controls import Keys, keymask
from desmume.emulator import SCREEN_HEIGHT, SCREEN_PIXEL_SIZE, SCREEN_WIDTH
from desmume.emulator import DeSmuME as BaseDeSmuME
from pygame.locals import QUIT
from ndspy.rom import NintendoDSRom


class Region(StrEnum):
    US = "E"
    EU = "P"
    JP = "J"


CONTROLS = {
    "enter": Keys.KEY_START,
    "right shift": Keys.KEY_SELECT,
    "q": Keys.KEY_L,
    "w": Keys.KEY_R,
    "a": Keys.KEY_Y,
    "s": Keys.KEY_X,
    "x": Keys.KEY_A,
    "z": Keys.KEY_B,
    "up": Keys.KEY_UP,
    "down": Keys.KEY_DOWN,
    "right": Keys.KEY_RIGHT,
    "left": Keys.KEY_LEFT,
    "l": Keys.KEY_LID,
}


def is_window_focused(desmume):
    if desmume.should_pause_when_unfocused:
        if win32gui.GetActiveWindow() == pygame.display.get_wm_info()['window'] or win32gui.GetActiveWindow() == win32gui.FindWindow(None, "ph-flag-finder-quick-settings"):
            DeSmuME.resume(desmume)
        else:
            DeSmuME.pause(desmume)


FAKE_MIC_BUTTON = "space"
MIC_ADDRESSES = {
    Region.US: 0x20EECCF,
    Region.EU: 0x20EED2F,
}


class DeSmuME(BaseDeSmuME):
    rom_region: Region
    has_quit: bool
    should_pause_when_unfocused: bool = True
    SCREEN_WIDTH: int = 256
    SCREEN_HEIGHT: int = 192
    SCREEN_HEIGHT_BOTH: int = SCREEN_HEIGHT * 2

    def __init__(self, refresh_rate: int = 60, dl_name: str | None = None):
        super().__init__(dl_name)

        self.has_quit = False

        self.pygame_screen = pygame.display.set_mode(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT_BOTH), pygame.RESIZABLE
        )
        pygame.display.set_caption("ph-flag-finder")
        pygame.event.set_allowed(QUIT)
        # Create another surface to draw on
        self.draw_surface = pygame.surface.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT_BOTH))

        # Starting timer to control the framerate
        self.clock = pygame.time.Clock()
        self._refresh_rate = refresh_rate

        self.controls_widget = Tk()
        self.controls_widget.title("ph-flag-finder-quick-settings")

        self._setup_controls()
        self.controls_widget.protocol("WM_DELETE_WINDOW", self.quit)

    def _setup_controls(self):
        def toggle_pause():
            self.should_pause_when_unfocused = not self.should_pause_when_unfocused
            pause["text"] = "Pause on unfocus: " + self.should_pause_when_unfocused.__str__()

        def update_refresh_rate(amount):
            self._refresh_rate = max(0, self._refresh_rate + amount)
            framerate["text"] = "(no limits)" if self._refresh_rate == 0 else self._refresh_rate

        def update_resolution(width, height):
            self.SCREEN_WIDTH += width
            self.SCREEN_HEIGHT_BOTH += height
            self.pygame_screen = pygame.display.set_mode(
                (self.SCREEN_WIDTH, self.SCREEN_HEIGHT_BOTH), pygame.RESIZABLE
            )
            resolution["text"] = pygame.display.get_window_size()

        def set_default_resolution():
            self.SCREEN_WIDTH = 256
            self.SCREEN_HEIGHT_BOTH = 192 * 2
            self.pygame_screen = pygame.display.set_mode(
                (self.SCREEN_WIDTH, self.SCREEN_HEIGHT_BOTH), pygame.RESIZABLE
            )
            resolution["text"] = pygame.display.get_window_size()

        Button(self.controls_widget, text="Decrease speed", command=lambda: update_refresh_rate(-10)).pack()
        Button(self.controls_widget, text="Increase speed", command=lambda: update_refresh_rate(10)).pack()
        Button(self.controls_widget, text="Set framerate to 60", command=lambda: update_refresh_rate(60 - self._refresh_rate)).pack()
        Button(self.controls_widget, text="Increase current resolution", command=lambda: update_resolution(32, 32)).pack()
        Button(self.controls_widget, text="Decrease current resolution", command=lambda: update_resolution(-32, -32)).pack()
        Button(self.controls_widget, text="Set default resolution", command=set_default_resolution).pack()
        Button(self.controls_widget, text="Toggle pause on unfocus", command=lambda: toggle_pause()).pack()

        framerate = Label(self.controls_widget, text="60")
        resolution = Label(self.controls_widget, text=pygame.display.get_window_size())
        pause = Label(self.controls_widget, text="Pause on unfocus: " + self.should_pause_when_unfocused.__str__())
        framerate.pack()
        resolution.pack()
        pause.pack()

    def quit(self):
        self.has_quit = True
        self.controls_widget.destroy()

    def open(self, file_name: str, auto_resume=True):
        rom = NintendoDSRom.fromFile(file_name)
        if rom.name.decode() != "ZELDA_DS:PH":
            raise ValueError("Invalid ROM!")
        self.rom_region = rom.idCode.decode()[3]
        return super().open(file_name, auto_resume)

    @cached_property
    def window_handle(self) -> int:
        return win32gui.FindWindow(None, "ph-flag-finder")

    def _cycle_pygame_window(self) -> None:
        # Get the framebuffer from the emulator
        gpu_framebuffer = self.display_buffer_as_rgbx()

        # Create surfaces from framebuffer
        upper_surface = pygame.image.frombuffer(
            gpu_framebuffer[: SCREEN_PIXEL_SIZE * 4],
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            "RGBX",
        )

        lower_surface = pygame.image.frombuffer(
            gpu_framebuffer[SCREEN_PIXEL_SIZE * 4:],
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            "RGBX",
        )

        # Draw the surfaces onto the draw surface
        self.draw_surface.blit(upper_surface, (0, 0))
        self.draw_surface.blit(lower_surface, (0, SCREEN_HEIGHT))

    def cycle(self, with_joystick=True) -> None:
        for event in pygame.event.get():
            if event.type == QUIT:
                self.quit()

        if self.has_quit:
            return
        is_window_focused(self)
        self._cycle_pygame_window()

        # Scale the draw surface to match the size of the screen and blit it on the screen
        self.pygame_screen.blit(
            pygame.transform.scale(
                self.draw_surface, self.pygame_screen.get_rect().size
            ),
            (0, 0),
        )
        pygame.display.flip()

        # Update control widget and handle input
        self.controls_widget.update()

        # Limit frame rate
        self.clock.tick(self._refresh_rate if self._refresh_rate > 0 else 0)

        for key, emulated_button in CONTROLS.items():
            if keyboard.is_pressed(key):
                self.input.keypad_add_key(keymask(emulated_button))
            else:
                self.input.keypad_rm_key(keymask(emulated_button))

        if keyboard.is_pressed(FAKE_MIC_BUTTON):
            self.memory.unsigned[MIC_ADDRESSES[self.rom_region]] = 0xFF

        # If mouse is clicked
        if win32api.GetKeyState(0x01) < 0:
            window_height = self.pygame_screen.get_height()
            window_width = self.pygame_screen.get_width()

            # Get coordinates of click relative to desmume window
            x, y = win32gui.ScreenToClient(self.window_handle, win32gui.GetCursorPos())

            # Adjust y coord to account for clicks on top (non-touch) screen
            y -= window_height // 2

            # Get scale factors in case the screen has been resized
            x_scale = window_width / self.SCREEN_WIDTH
            y_scale = window_height / self.SCREEN_HEIGHT_BOTH
            x = max(int(x / x_scale), 0)
            y = max(int(y / y_scale), 0)
            self.input.touch_set_pos(x, y)
        else:
            self.input.touch_release()

        super().cycle(with_joystick)
