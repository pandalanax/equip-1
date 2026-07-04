import time
import shutil
import subprocess
import os
import glob
import socket
from periphery import GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from PIL import Image, ImageDraw, ImageFont
from luma.core.error import DeviceNotFoundError

# Set to "rock2f" or "rpi"
BOARD = os.environ.get("EQUIP_1_BOARD_TYPE", "rock2f")

if BOARD == "rock2f":
    I2C_PORT = 0
    GPIOCHIP = "/dev/gpiochip4"
    BUZZER = 19
    # Hardware PWM for the buzzer: PWM0 (GPIO4_C3) at ffa90000. Matched against
    # /sys/class/pwm/pwmchip*/device so the chip number can float.
    BUZZER_PWM_ADDR = "ffa90000"
    BTN_UP = 15
    BTN_SELECT = 16
    BTN_DOWN = 22
elif BOARD == "rpi":
    I2C_PORT = 1
    GPIOCHIP = "/dev/gpiochip4"
    BUZZER = 12
    BUZZER_PWM_ADDR = None
    BTN_UP = 22
    BTN_SELECT = 27
    BTN_DOWN = 17
else:
    raise ValueError(f"Unknown BOARD: {BOARD}")


class RecorderState:
    def __init__(self, output_dir=None):
        if output_dir is None:
            # Recordings go to the exFAT data partition (mounted at /data by
            # S15data), which is readable on macOS/Windows.
            output_dir = os.environ.get("EQUIP_1_CAPTURES_DIR", "/data/captures")
        self.mode = "idle"
        self.start_time = None
        self.process = None
        self.last_error = None
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    @property
    def camera_connected(self):
        # Check if a FireWire camera is connected (fw1 exists when camera plugged in)
        return os.path.exists("/dev/fw1")

    def toggle(self):
        if self.mode == "idle":
            if not self.camera_connected:
                return
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            try:
                self.process = subprocess.Popen(
                    ["dvgrab", "-buffers", "20",
                     f"{self.output_dir}/capture_{timestamp}-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            except (FileNotFoundError, OSError) as exc:
                # Capture tool missing or failed to launch: stay idle and surface
                # the error instead of crashing the whole app.
                print(f"Recording failed to start: {exc}")
                self.process = None
                self.last_error = "REC ERR"
                return
            self.mode = "recording"
            self.start_time = time.time()
            self.last_error = None
        else:
            self.mode = "idle"
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.process = None
            self.start_time = None

    @property
    def is_recording(self):
        return self.mode == "recording"

    @property
    def elapsed_text(self):
        if not self.is_recording or self.start_time is None:
            return "00:00:00"
        elapsed = time.time() - self.start_time
        hh, rem = divmod(int(elapsed), 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02}:{mm:02}:{ss:02}"

    @property
    def recording_minutes_left(self):
        _, _, free = shutil.disk_usage(self.output_dir)
        # DV video around 3.6 MB/s = 216 MB/min
        # How could we know bitrate of different cameras?
        minutes = free / (216 * 1024 * 1024)
        return f"{int(minutes)}m"


class Display:
    def __init__(self):
        serial = i2c(port=I2C_PORT, address=0x3C)
        self.device = sh1106(serial)
        self.font_medium = ImageFont.truetype(
            "fonts/Px437_DOS-V_re_JPN12.ttf", 12
        )
        self.font_big = ImageFont.truetype(
            "fonts/Px437_Paradise132_7x16.ttf", 34
        )

    @property
    def width(self):
        return self.device.width

    @property
    def height(self):
        return self.device.height

    def clear(self):
        img = Image.new("1", self.device.size)
        self.device.display(img)

    def render(self, draw_func):
        img = Image.new("1", self.device.size)
        draw = ImageDraw.Draw(img)
        draw_func(draw, self.device.width, self.device.height)
        self.device.display(img)


class NullDisplay:
    def __init__(self):
        self.width = 128
        self.height = 64
        self.font_medium = ImageFont.load_default()
        self.font_big = ImageFont.load_default()

    def clear(self):
        pass

    def render(self, draw_func):
        pass


class Screen:    
    def __init__(self, app):
        self.app = app
    
    def on_select(self):
        pass
    
    def can_navigate(self):
        return True
    
    def render(self, draw, width, height):
        pass


class RecordingScreen(Screen):
    def on_select(self):
        self.app.recorder.toggle()
    
    def can_navigate(self):
        return not self.app.recorder.is_recording
    
    def render(self, draw, width, height):
        recorder = self.app.recorder
        font_medium = self.app.display.font_medium
        font_big = self.app.display.font_big
        
        # No camera connected
        if not recorder.camera_connected and not recorder.is_recording:
            draw.text((0, 0), "RECORD", font=font_medium, fill=255)
            no_cam = "NO CAM"
            bbox = draw.textbbox((0, 0), no_cam, font=font_big)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, 28), no_cam, font=font_big, fill=255)
            return
        
        # Recording indicator
        if recorder.is_recording:
            if int(time.time() * 2) % 2:
                draw.ellipse((0, 2, 10, 12), fill=255)
            draw.text((14, 0), "REC", font=font_medium, fill=255)
        else:
            draw.text((0, 0), "RECORD", font=font_medium, fill=255)
            # Surface a failed capture launch instead of silently doing nothing.
            if recorder.last_error:
                bbox = draw.textbbox((0, 0), recorder.last_error, font=font_big)
                x = (width - (bbox[2] - bbox[0])) // 2
                draw.text((x, 28), recorder.last_error, font=font_big, fill=255)
                return
        
        # Minutes left (top right)
        mins_left = recorder.recording_minutes_left
        bbox = draw.textbbox((0, 0), mins_left, font=font_medium)
        draw.text((width - (bbox[2] - bbox[0]), 0), mins_left, font=font_medium, fill=255)
        
        # Timer (center)
        timer = recorder.elapsed_text
        bbox = draw.textbbox((0, 0), timer, font=font_big)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, 28), timer, font=font_big, fill=255)


class StorageScreen(Screen):
    def render(self, draw, width, height):
        font_medium = self.app.display.font_medium
        
        draw.text((0, 0), "STORAGE", font=font_medium, fill=255)
        
        total, used, free = shutil.disk_usage(self.app.recorder.output_dir)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        percent = (used / total) * 100
        
        draw.text((0, 16), f"Total: {total_gb:.1f} GB", font=font_medium, fill=255)
        draw.text((0, 30), f"Used:  {used_gb:.1f} GB ({percent:.0f}%)", font=font_medium, fill=255)
        draw.text((0, 44), f"Free:  {free_gb:.1f} GB", font=font_medium, fill=255)


class NetworkScreen(Screen):
    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "No connection"
    
    def render(self, draw, width, height):
        font_medium = self.app.display.font_medium
        
        draw.text((0, 0), "NETWORK", font=font_medium, fill=255)
        
        ip = self.get_ip()
        draw.text((0, 20), "IP Address:", font=font_medium, fill=255)
        draw.text((0, 34), ip, font=font_medium, fill=255)


class USBGadgetScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.enabled = False
    
    def on_select(self):
        self.enabled = not self.enabled
        if self.enabled:
            subprocess.run(["modprobe", "g_mass_storage", 
                          f"file={self.app.recorder.output_dir}", "removable=1"],
                          capture_output=True)
        else:
            subprocess.run(["modprobe", "-r", "g_mass_storage"], capture_output=True)
    
    def render(self, draw, width, height):
        font_medium = self.app.display.font_medium
        
        draw.text((0, 0), "USB GADGET", font=font_medium, fill=255)
        
        status = "ENABLED" if self.enabled else "DISABLED"
        draw.text((0, 20), "Mass Storage Mode:", font=font_medium, fill=255)
        draw.text((0, 34), status, font=font_medium, fill=255)
        draw.text((0, 50), "Press to toggle", font=font_medium, fill=255)


class PowerScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.options = ["Shutdown", "Reboot", "Cancel"]
        self.selected = 0
        self.confirm_mode = False
    
    def on_select(self):
        if not self.confirm_mode:
            self.confirm_mode = True
        else:
            if self.options[self.selected] == "Shutdown":
                subprocess.run(["sudo", "shutdown", "-h", "now"])
            elif self.options[self.selected] == "Reboot":
                subprocess.run(["sudo", "reboot"])
            else:
                self.confirm_mode = False
                self.selected = 0
    
    def on_up(self):
        if self.confirm_mode:
            self.selected = (self.selected - 1) % len(self.options)
            return True
        return False
    
    def on_down(self):
        if self.confirm_mode:
            self.selected = (self.selected + 1) % len(self.options)
            return True
        return False
    
    def render(self, draw, width, height):
        font_medium = self.app.display.font_medium
        
        draw.text((0, 0), "POWER", font=font_medium, fill=255)
        
        if not self.confirm_mode:
            draw.text((0, 20), "Press to select:", font=font_medium, fill=255)
            draw.text((0, 34), "Shutdown / Reboot", font=font_medium, fill=255)
        else:
            for i, opt in enumerate(self.options):
                y = 16 + i * 16
                prefix = "> " if i == self.selected else "  "
                draw.text((0, y), prefix + opt, font=font_medium, fill=255)


class TestScreen(Screen):
    def render(self, draw, width, height):
        draw.rectangle((0, 0, width, height), fill=255)



class Buzzer:
    """Drives the passive buzzer. Prefers jitter-free hardware PWM via sysfs;
    falls back to software bit-banging on a plain GPIO if no PWM channel is found."""

    def __init__(self, chip=GPIOCHIP, line=BUZZER, pwm_addr=BUZZER_PWM_ADDR):
        self.pwm = None   # path to /sys/class/pwm/pwmchipN/pwm0 when using hardware PWM
        self.gpio = None
        pwmchip = self._find_pwmchip(pwm_addr) if pwm_addr else None
        if pwmchip is not None:
            self.pwm = self._export_pwm(pwmchip)
        if self.pwm is None:
            # Fallback: bit-banged square wave on a GPIO (jittery, but works).
            self.gpio = GPIO(chip, line, "out")

    @staticmethod
    def _find_pwmchip(addr):
        for chip in glob.glob("/sys/class/pwm/pwmchip*"):
            try:
                if addr in os.path.realpath(os.path.join(chip, "device")):
                    return chip
            except OSError:
                pass
        return None

    def _export_pwm(self, chip):
        channel = os.path.join(chip, "pwm0")
        try:
            if not os.path.isdir(channel):
                with open(os.path.join(chip, "export"), "w") as f:
                    f.write("0")
            return channel
        except OSError:
            return None

    def _write(self, attr, value):
        with open(os.path.join(self.pwm, attr), "w") as f:
            f.write(str(value))

    def beep(self, duration=0.08, freq=2048):
        if self.pwm is not None:
            period = int(1_000_000_000 / freq)  # nanoseconds
            try:
                # period must be set before duty_cycle (a freshly exported channel
                # has period=0, and writing duty_cycle then fails with EINVAL).
                try:
                    self._write("period", period)
                except OSError:
                    # current duty_cycle exceeds the new period: zero it, then retry
                    self._write("duty_cycle", 0)
                    self._write("period", period)
                self._write("duty_cycle", period // 2)
                self._write("enable", 1)
                time.sleep(duration)
                self._write("enable", 0)
            except OSError:
                pass
            return
        # Software fallback
        cycles = int(duration * freq)
        half_period = 1.0 / freq / 2
        for _ in range(cycles):
            self.gpio.write(True)
            time.sleep(half_period)
            self.gpio.write(False)
            time.sleep(half_period)

    def close(self):
        if self.pwm is not None:
            try:
                self._write("enable", 0)
            except OSError:
                pass
        if self.gpio is not None:
            self.gpio.close()


class NullBuzzer:
    def beep(self, duration=0.08, freq=2048):
        pass

    def close(self):
        pass


class Button:
    def __init__(self, chip, line):
        self.gpio = GPIO(chip, line, "in")
        self.last_state = True
        self.last_press = 0

    def pressed(self):
        current = self.gpio.read()
        now = time.time()

        if self.last_state and not current and (now - self.last_press) > 0.3:
            self.last_press = now
            self.last_state = current
            return True

        self.last_state = current
        return False

    def close(self):
        self.gpio.close()


class Buttons:
    def __init__(self):
        self.up = Button(GPIOCHIP, BTN_UP)
        self.select = Button(GPIOCHIP, BTN_SELECT)
        self.down = Button(GPIOCHIP, BTN_DOWN)
 
    def close(self):
        self.up.close()
        self.select.close()
        self.down.close()


class NullButton:
    def pressed(self):
        return False


class NullButtons:
    def __init__(self):
        self.up = NullButton()
        self.select = NullButton()
        self.down = NullButton()

    def close(self):
        pass


class App:
    def __init__(self):
        self.recorder = RecorderState()
        self.display = self._create_display()
        self.buttons = self._create_buttons()
        self.buzzer = self._create_buzzer()
        
        self.screens = [
            #TestScreen(self),
            RecordingScreen(self),
            StorageScreen(self),
            NetworkScreen(self),
            #USBGadgetScreen(self),
            PowerScreen(self),
        ]
        self.current_screen_idx = 0

    def _create_display(self):
        try:
            return Display()
        except (FileNotFoundError, DeviceNotFoundError, OSError) as exc:
            print(f"Display unavailable, running headless: {exc}")
            return NullDisplay()

    def _create_buttons(self):
        try:
            return Buttons()
        except (FileNotFoundError, OSError) as exc:
            print(f"Buttons unavailable, continuing without GPIO input: {exc}")
            return NullButtons()

    def _create_buzzer(self):
        try:
            return Buzzer()
        except (FileNotFoundError, OSError) as exc:
            print(f"Buzzer unavailable, continuing without GPIO output: {exc}")
            return NullBuzzer()
    
    @property
    def current_screen(self):
        return self.screens[self.current_screen_idx]
    
    def navigate_up(self):
        if hasattr(self.current_screen, 'on_up') and self.current_screen.on_up():
            return
        
        if self.current_screen.can_navigate():
            self.current_screen_idx = (self.current_screen_idx - 1) % len(self.screens)
    
    def navigate_down(self):
        if hasattr(self.current_screen, 'on_down') and self.current_screen.on_down():
            return
        
        if self.current_screen.can_navigate():
            self.current_screen_idx = (self.current_screen_idx + 1) % len(self.screens)
    
    def startup(self):
        """Boot splash: 'EQUIP-1' types out in the logo font with an ascending
        buzzer jingle, then a final note. Safe with NullDisplay/NullBuzzer."""
        title = "EQUIP-1"
        disp = self.display

        # Logo font (w.ttf), auto-sized to the largest that fits the width.
        probe = ImageDraw.Draw(Image.new("1", (disp.width, disp.height)))
        fb = disp.font_big
        for size in (44, 40, 36, 32, 30, 28, 26, 24, 22):
            try:
                f = ImageFont.truetype("fonts/w.ttf", size)
            except OSError:
                break
            bbox = probe.textbbox((0, 0), title, font=f)
            if (bbox[2] - bbox[0]) <= disp.width - 4:
                fb = f
                break

        for n in range(1, len(title) + 1):
            partial = title[:n]

            def draw(d, w, h, partial=partial):
                bbox = d.textbbox((0, 0), title, font=fb)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = (w - tw) // 2 - bbox[0]
                y = (h - th) // 2 - bbox[1]
                d.text((x, y), partial, font=fb, fill=255)

            disp.render(draw)
            self.buzzer.beep(duration=0.05, freq=500 + n * 90)
            time.sleep(0.04)

        self.buzzer.beep(duration=0.20, freq=1047)
        time.sleep(0.5)

    def run(self):
        try:
            self.startup()
        except Exception as exc:
            # Never let a splash error take down the whole app.
            print(f"startup splash failed: {exc}")
        try:
            while True:
                if self.buttons.up.pressed():
                    self.buzzer.beep()
                    self.navigate_up()
                
                if self.buttons.down.pressed():
                    self.buzzer.beep()
                    self.navigate_down()
                
                if self.buttons.select.pressed():
                    self.buzzer.beep()
                    self.current_screen.on_select()
                
                self.display.render(self.current_screen.render)
                time.sleep(0.05)
        
        except KeyboardInterrupt:
            pass
        finally:
            if self.recorder.is_recording:
                self.recorder.toggle()
            self.buttons.close()
            self.buzzer.close()


def main():
    app = App()
    app.run()

if __name__ == "__main__":
    main()
