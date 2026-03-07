import atexit
import io
import logging
import os
import threading
import time
from pathlib import Path

import pillow_heif
import pystray
import win32api
import win32clipboard
import win32event
import winerror
from PIL import Image
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# HEIC/HEIF 지원 활성화
pillow_heif.register_heif_opener()

# ===== 설정 =====
WATCH_DIRECTORIES = [
    r"D:\Downloads",
    r"C:\Users\minsang\Downloads",
]

# 변환 대상 확장자 (소문자)
CONVERT_EXTENSIONS = {
    ".webp",    # 웹용 최신 형식
    ".heic",    # iPhone 사진
    ".heif",    # iPhone 사진
    ".avif",    # AV1 기반
    ".bmp",     # 비압축 비트맵
    ".tiff",    # 출판/인쇄용
    ".tif",     # TIFF 별칭
    ".ico",     # 아이콘
    ".jxl",     # JPEG XL
}

# 변환하지 않을 확장자 (일반적인 형식)
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif"}

# 스크립트가 직접 생성한 파일을 재처리하지 않기 위한 무시 시간
INTERNAL_FILE_IGNORE_SECONDS = 10
APP_MUTEX_NAME = "Local\\ImageConverterSingleton"
LOG_FILE_PATH = Path(__file__).with_name("image_converter.log")

# ===== 로깅 설정 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
app_mutex = None


# ===== 전역 상태 =====
class AppState:
    """애플리케이션 상태 관리"""

    def __init__(self):
        self.paused = False
        self.observer = None
        self.tray_icon = None
        self.watch_directories = []
        self.observer_ready = threading.Event()
        self.observer_failed = threading.Event()


app_state = AppState()


def acquire_single_instance() -> bool:
    """이미 실행 중인 프로세스가 있으면 False를 반환합니다."""
    global app_mutex

    mutex = win32event.CreateMutex(None, True, APP_MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.CloseHandle(mutex)
        return False

    app_mutex = mutex
    return True


def release_single_instance():
    """프로세스 종료 시 뮤텍스를 정리합니다."""
    global app_mutex

    if app_mutex is None:
        return

    try:
        win32event.ReleaseMutex(app_mutex)
    except Exception:
        pass

    try:
        win32api.CloseHandle(app_mutex)
    except Exception:
        pass

    app_mutex = None


atexit.register(release_single_instance)


def resolve_watch_directories() -> list[Path]:
    """실제로 감시 가능한 폴더 목록을 반환합니다."""
    resolved_directories = []
    seen_paths = set()

    for raw_path in WATCH_DIRECTORIES:
        normalized_path = os.path.normcase(os.path.abspath(raw_path))
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)

        path = Path(raw_path)
        if path.is_dir():
            resolved_directories.append(path)
        elif path.exists():
            logger.warning(f"⚠️ 감시 경로가 폴더가 아니어서 건너뜁니다: {path}")
        else:
            logger.warning(f"⚠️ 모니터링 폴더가 없어 건너뜁니다: {path}")

    return resolved_directories


def create_icon_image(color: str = "green"):
    """트레이 아이콘 이미지 생성 (녹색=활성, 빨간색=일시정지)"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    
    # 원 그리기
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    
    if color == "green":
        fill_color = (76, 175, 80, 255)  # 녹색
    else:
        fill_color = (244, 67, 54, 255)  # 빨간색
    
    # 외곽선 그리기
    draw.ellipse([4, 4, size-4, size-4], fill=fill_color, outline=(255, 255, 255, 255), width=2)
    
    # 중앙에 이미지 아이콘 모양 (간단한 사각형)
    margin = 18
    draw.rectangle([margin, margin, size-margin, size-margin], fill=(255, 255, 255, 200))
    
    return img


def copy_image_to_clipboard(image_path: str):
    """
    이미지를 Windows 클립보드에 복사합니다.
    Ctrl+V로 바로 붙여넣기 가능!
    """
    clipboard_image = None
    clipboard_open = False

    try:
        # PNG 이미지를 BMP로 변환 (클립보드용)
        with Image.open(image_path) as opened_image:
            # RGBA -> RGB 변환 (BMP는 알파 채널 미지원)
            if opened_image.mode == "RGBA":
                clipboard_image = Image.new("RGB", opened_image.size, (255, 255, 255))
                clipboard_image.paste(opened_image, mask=opened_image.getchannel("A"))
            elif opened_image.mode != "RGB":
                clipboard_image = opened_image.convert("RGB")
            else:
                clipboard_image = opened_image.copy()

        # BMP 형식으로 메모리에 저장
        with io.BytesIO() as output:
            clipboard_image.save(output, "BMP")
            bmp_data = output.getvalue()[14:]  # BMP 헤더 14바이트 제거

        # 다른 앱이 클립보드를 점유 중일 수 있어 짧게 재시도
        for attempt in range(5):
            try:
                win32clipboard.OpenClipboard()
                clipboard_open = True
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(0.2)

        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        
        logger.info(f"📋 클립보드에 복사됨: {Path(image_path).name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 클립보드 복사 실패: {e}")
        return False

    finally:
        if clipboard_open:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        if clipboard_image is not None:
            clipboard_image.close()


def build_png_destination(source_path: str) -> Path:
    """저장 가능한 PNG 경로를 생성합니다."""
    source = Path(source_path)
    dest_path = source.with_suffix(".png")

    # 동일한 이름의 PNG가 이미 있으면 번호 추가
    counter = 1
    while dest_path.exists():
        dest_path = source.with_name(f"{source.stem}_{counter}.png")
        counter += 1

    return dest_path


def convert_to_png(source_path: str, dest_path: Path) -> str | None:
    """
    이미지를 PNG로 변환합니다.
    
    Args:
        source_path: 원본 이미지 경로
        dest_path: 변환된 PNG 저장 경로
        
    Returns:
        변환된 PNG 파일 경로 (실패 시 None)
    """
    converted_image = None

    try:
        source = Path(source_path)

        # 이미지 열기 및 변환
        with Image.open(source_path) as opened_image:
            # RGBA 모드로 변환 (PNG는 투명도 지원)
            if opened_image.mode == "RGBA":
                converted_image = opened_image.copy()
            else:
                converted_image = opened_image.convert("RGBA")

        # PNG로 저장
        converted_image.save(dest_path, "PNG")
        
        logger.info(f"✅ 변환 완료: {source.name} → {dest_path.name}")
        return str(dest_path)
        
    except Exception as e:
        logger.error(f"❌ 변환 실패 [{source_path}]: {e}")
        return None

    finally:
        if converted_image is not None:
            converted_image.close()


def delete_original(file_path: str):
    """원본 파일을 삭제합니다."""
    try:
        os.remove(file_path)
        logger.info(f"🗑️ 원본 삭제됨: {Path(file_path).name}")
    except Exception as e:
        logger.error(f"❌ 삭제 실패 [{file_path}]: {e}")


class ImageHandler(FileSystemEventHandler):
    """파일 생성 이벤트를 처리하는 핸들러"""
    
    def __init__(self):
        super().__init__()
        self.processing = set()  # 중복 처리 방지
        self.ignored_paths = {}  # 스크립트가 직접 생성한 파일 무시

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        """중복 비교용 경로 표준화"""
        return os.path.normcase(os.path.abspath(file_path))

    def _prune_ignored_paths(self):
        """만료된 무시 목록 제거"""
        current_time = time.monotonic()
        expired_paths = [
            path for path, expires_at in self.ignored_paths.items()
            if expires_at <= current_time
        ]
        for path in expired_paths:
            self.ignored_paths.pop(path, None)

    def _mark_ignored(self, file_path: str, ttl: int = INTERNAL_FILE_IGNORE_SECONDS):
        """스크립트가 생성한 파일을 일정 시간 무시"""
        normalized_path = self._normalize_path(file_path)
        self.ignored_paths[normalized_path] = time.monotonic() + ttl
    
    def on_created(self, event):
        """새 파일이 생성되면 호출됩니다."""
        if event.is_directory:
            return
        self._process_file(event.src_path)
    
    def on_moved(self, event):
        """파일이 이동/이름 변경되면 호출됩니다.
        브라우저가 다운로드할 때 임시 파일(.tmp, .crdownload)을
        최종 파일명으로 변경하는 경우를 처리합니다.
        """
        if event.is_directory:
            return
        # 이동된 파일의 최종 경로를 처리
        self._process_file(event.dest_path)
    
    def _process_file(self, file_path: str):
        """이미지 파일을 처리합니다."""
        # 일시정지 상태면 무시
        if app_state.paused:
            return
        
        ext = Path(file_path).suffix.lower()
        
        # 이미지 파일인지 확인 (변환 대상 + 일반 형식 모두)
        all_image_extensions = CONVERT_EXTENSIONS | SKIP_EXTENSIONS
        if ext not in all_image_extensions:
            return

        normalized_path = self._normalize_path(file_path)
        self._prune_ignored_paths()

        # 스크립트가 방금 만든 파일은 무시
        if normalized_path in self.ignored_paths:
            return

        # 중복 처리 방지
        if normalized_path in self.processing:
            return
        self.processing.add(normalized_path)
        
        try:
            # 파일 쓰기 완료 대기 (다운로드 중일 수 있음)
            self._wait_for_file_ready(file_path)
            
            logger.info(f"🔍 감지됨: {Path(file_path).name}")
            
            # 비일반적 형식 → PNG로 변환 후 클립보드 복사
            if ext in CONVERT_EXTENSIONS:
                dest_path = build_png_destination(file_path)
                self._mark_ignored(str(dest_path))
                png_path = convert_to_png(file_path, dest_path)
                
                if png_path:
                    # 클립보드에 복사
                    if copy_image_to_clipboard(png_path):
                        # 클립보드 복사까지 성공한 경우에만 원본 삭제
                        delete_original(file_path)
                    else:
                        logger.warning(f"⚠️ 클립보드 복사 실패로 원본 유지: {Path(file_path).name}")
            
            # 일반적 형식 → 바로 클립보드 복사 (변환 없음)
            elif ext in SKIP_EXTENSIONS:
                copy_image_to_clipboard(file_path)
        
        finally:
            self.processing.discard(normalized_path)
    
    def _wait_for_file_ready(self, file_path: str, timeout: int = 30):
        """
        파일 쓰기가 완료될 때까지 대기합니다.
        (다운로드 중인 파일은 크기가 계속 변함)
        """
        last_size = -1
        stable_count = 0
        
        for _ in range(timeout * 2):  # 0.5초 간격
            try:
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= 3:  # 1.5초간 크기 변화 없음
                        return
                else:
                    stable_count = 0
                last_size = current_size
            except OSError:
                pass
            time.sleep(0.5)

        logger.warning(f"⚠️ 파일 준비 시간 초과, 현재 상태로 처리합니다: {Path(file_path).name}")


# ===== 트레이 메뉴 핸들러 =====
def on_toggle_pause(icon, item):
    """일시정지/재개 토글"""
    app_state.paused = not app_state.paused
    
    if app_state.paused:
        logger.info("⏸️ 일시정지됨")
        icon.icon = create_icon_image("red")
    else:
        logger.info("▶️ 재개됨")
        icon.icon = create_icon_image("green")
    
    # 메뉴 업데이트
    icon.update_menu()


def on_exit(icon, item):
    """종료"""
    logger.info("🛑 종료 요청됨...")
    
    # 감시자 중지
    if app_state.observer:
        app_state.observer.stop()
    
    # 트레이 아이콘 제거
    icon.stop()


def get_pause_text(item):
    """일시정지 메뉴 텍스트"""
    return "▶️ 재개" if app_state.paused else "⏸️ 일시정지"


def run_tray_icon():
    """시스템 트레이 아이콘 실행"""
    menu = pystray.Menu(
        pystray.MenuItem(get_pause_text, on_toggle_pause),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ 종료", on_exit)
    )
    
    icon = pystray.Icon(
        "ImageConverter",
        create_icon_image("green"),
        "이미지 자동 변환",
        menu
    )
    
    app_state.tray_icon = icon
    try:
        icon.run()
    finally:
        if app_state.observer:
            app_state.observer.stop()


def run_observer(watch_directories: list[Path]):
    """파일 감시자 실행 (별도 스레드)"""
    logger.info("=" * 50)
    logger.info("🚀 이미지 자동 변환 스크립트 시작")
    logger.info("📁 모니터링 폴더:")
    for watch_directory in watch_directories:
        logger.info(f"   - {watch_directory}")
    logger.info(f"📝 변환 대상: {', '.join(sorted(CONVERT_EXTENSIONS))}")
    logger.info(f"📋 클립보드 복사: 모든 이미지 ({', '.join(sorted(SKIP_EXTENSIONS))} 포함)")
    logger.info("💡 시스템 트레이에서 제어 가능")
    logger.info("=" * 50)
    
    # 감시자 설정
    event_handler = ImageHandler()
    observer = Observer()
    for watch_directory in watch_directories:
        observer.schedule(event_handler, str(watch_directory), recursive=False)
    
    app_state.observer = observer
    
    try:
        # 감시 시작
        observer.start()
        app_state.observer_ready.set()

        while observer.is_alive():
            observer.join(timeout=1)
    except Exception:
        if not app_state.observer_ready.is_set():
            app_state.observer_failed.set()
            app_state.observer_ready.set()
        logger.exception("❌ 파일 감시 중 오류 발생")
    finally:
        if observer.is_alive():
            observer.stop()
            observer.join(timeout=5)

        logger.info("스크립트 종료")

        if app_state.tray_icon:
            app_state.tray_icon.stop()


def main():
    """메인 함수"""
    if not acquire_single_instance():
        logger.warning("⚠️ 이미 실행 중인 인스턴스가 있어 종료합니다.")
        return

    watch_directories = resolve_watch_directories()
    if not watch_directories:
        logger.error("❌ 사용할 모니터링 폴더가 없습니다. WATCH_DIRECTORIES 설정을 확인하세요.")
        return

    app_state.watch_directories = watch_directories
    app_state.observer_ready.clear()
    app_state.observer_failed.clear()

    # 파일 감시자를 별도 스레드에서 실행
    observer_thread = threading.Thread(target=run_observer, args=(watch_directories,), daemon=True)
    observer_thread.start()

    if not app_state.observer_ready.wait(timeout=5):
        logger.error("❌ 파일 감시 시작이 지연되어 프로그램을 종료합니다.")
        if app_state.observer:
            app_state.observer.stop()
        observer_thread.join(timeout=5)
        return

    if app_state.observer_failed.is_set():
        logger.error("❌ 파일 감시를 시작하지 못했습니다.")
        observer_thread.join(timeout=5)
        return

    # 트레이 아이콘 실행 (메인 스레드에서)
    try:
        run_tray_icon()
    finally:
        if app_state.observer:
            app_state.observer.stop()
        observer_thread.join(timeout=5)


if __name__ == "__main__":
    main()
