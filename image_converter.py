"""
이미지 자동 변환 스크립트

D:\\Downloads 폴더를 모니터링하여 WebP, HEIC 등 비일반적인 이미지 형식을
자동으로 PNG로 변환합니다.

기능:
- 폴더 실시간 모니터링 (watchdog)
- 이미지 형식 변환 (Pillow + pillow-heif)
- 변환된 이미지 클립보드 복사 (pywin32)
- 변환 후 원본 삭제
- 시스템 트레이 아이콘 (pystray)
"""

import os
import time
import io
import logging
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
import pillow_heif
import win32clipboard
import pystray

# HEIC/HEIF 지원 활성화
pillow_heif.register_heif_opener()

# ===== 설정 =====
WATCH_DIR = r"D:\Downloads"  # 모니터링할 폴더

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

# ===== 로깅 설정 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ===== 전역 상태 =====
class AppState:
    """애플리케이션 상태 관리"""
    def __init__(self):
        self.paused = False
        self.observer = None
        self.tray_icon = None
        
app_state = AppState()


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
    try:
        # PNG 이미지를 BMP로 변환 (클립보드용)
        img = Image.open(image_path)
        
        # RGBA -> RGB 변환 (BMP는 알파 채널 미지원)
        if img.mode == "RGBA":
            # 흰색 배경에 합성
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        # BMP 형식으로 메모리에 저장
        output = io.BytesIO()
        img.save(output, "BMP")
        bmp_data = output.getvalue()[14:]  # BMP 헤더 14바이트 제거
        output.close()
        
        # 클립보드에 복사
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        win32clipboard.CloseClipboard()
        
        logger.info(f"📋 클립보드에 복사됨: {Path(image_path).name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 클립보드 복사 실패: {e}")
        return False


def convert_to_png(source_path: str) -> str | None:
    """
    이미지를 PNG로 변환합니다.
    
    Args:
        source_path: 원본 이미지 경로
        
    Returns:
        변환된 PNG 파일 경로 (실패 시 None)
    """
    try:
        source = Path(source_path)
        dest_path = source.with_suffix(".png")
        
        # 동일한 이름의 PNG가 이미 있으면 번호 추가
        counter = 1
        while dest_path.exists():
            dest_path = source.with_name(f"{source.stem}_{counter}.png")
            counter += 1
        
        # 이미지 열기 및 변환
        with Image.open(source_path) as img:
            # RGBA 모드로 변환 (PNG는 투명도 지원)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            
            # PNG로 저장
            img.save(dest_path, "PNG")
        
        logger.info(f"✅ 변환 완료: {source.name} → {dest_path.name}")
        return str(dest_path)
        
    except Exception as e:
        logger.error(f"❌ 변환 실패 [{source_path}]: {e}")
        return None


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
    
    def on_created(self, event):
        """새 파일이 생성되면 호출됩니다."""
        # 일시정지 상태면 무시
        if app_state.paused:
            return
            
        if event.is_directory:
            return
        
        file_path = event.src_path
        ext = Path(file_path).suffix.lower()
        
        # 이미지 파일인지 확인 (변환 대상 + 일반 형식 모두)
        all_image_extensions = CONVERT_EXTENSIONS | SKIP_EXTENSIONS
        if ext not in all_image_extensions:
            return
        
        # 중복 처리 방지
        if file_path in self.processing:
            return
        self.processing.add(file_path)
        
        try:
            # 파일 쓰기 완료 대기 (다운로드 중일 수 있음)
            self._wait_for_file_ready(file_path)
            
            logger.info(f"🔍 감지됨: {Path(file_path).name}")
            
            # 비일반적 형식 → PNG로 변환 후 클립보드 복사
            if ext in CONVERT_EXTENSIONS:
                png_path = convert_to_png(file_path)
                
                if png_path:
                    # 클립보드에 복사
                    copy_image_to_clipboard(png_path)
                    
                    # 원본 삭제
                    delete_original(file_path)
            
            # 일반적 형식 → 바로 클립보드 복사 (변환 없음)
            elif ext in SKIP_EXTENSIONS:
                copy_image_to_clipboard(file_path)
        
        finally:
            self.processing.discard(file_path)
    
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
    icon.run()


def run_observer():
    """파일 감시자 실행 (별도 스레드)"""
    # 모니터링 폴더 확인
    if not os.path.exists(WATCH_DIR):
        logger.error(f"❌ 폴더가 존재하지 않습니다: {WATCH_DIR}")
        return
    
    logger.info("=" * 50)
    logger.info("🚀 이미지 자동 변환 스크립트 시작")
    logger.info(f"📁 모니터링 폴더: {WATCH_DIR}")
    logger.info(f"📝 변환 대상: {', '.join(sorted(CONVERT_EXTENSIONS))}")
    logger.info(f"📋 클립보드 복사: 모든 이미지 ({', '.join(sorted(SKIP_EXTENSIONS))} 포함)")
    logger.info("💡 시스템 트레이에서 제어 가능")
    logger.info("=" * 50)
    
    # 감시자 설정
    event_handler = ImageHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    
    app_state.observer = observer
    
    # 감시 시작
    observer.start()
    
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except Exception:
        pass
    
    logger.info("� 스크립트 종료")


def main():
    """메인 함수"""
    # 파일 감시자를 별도 스레드에서 실행
    observer_thread = threading.Thread(target=run_observer, daemon=True)
    observer_thread.start()
    
    # 트레이 아이콘 실행 (메인 스레드에서)
    run_tray_icon()


if __name__ == "__main__":
    main()
