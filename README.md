# Image Converter

다운로드 폴더를 실시간 모니터링하여 WebP, HEIC 등 비일반적인 이미지 형식을 PNG로 자동 변환하는 Windows용 스크립트입니다.

## ✨ 주요 기능

- **자동 변환**: WebP, HEIC, AVIF, BMP, TIFF 등 → PNG
- **클립보드 복사**: 모든 이미지 다운로드 시 자동으로 클립보드에 복사 (Ctrl+V로 바로 붙여넣기)
- **트레이 아이콘**: 시스템 트레이에서 일시정지/종료 제어
- **프로젝트 로컬 실행 환경**: 프로젝트 폴더 안의 `.venv`만 사용
- **자동 시작**: Windows 부팅 시 백그라운드 실행 가능
- **중복 실행 방지**: 이미 실행 중이면 추가 인스턴스 자동 종료

## 📦 설치

```bash
# 프로젝트 폴더 안에 가상환경 생성
python -m venv .venv
.venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

## 🚀 실행

### 콘솔에서 실행
```bash
.venv\Scripts\python image_converter.py
```

### 백그라운드 실행 (콘솔 창 없이)
```bash
run_converter.bat
```

`run_converter.bat`는 현재 프로젝트 내부의 `.venv\Scripts\pythonw.exe`를 사용합니다.

문제 추적용 로그는 프로젝트 폴더의 `image_converter.log`에 저장됩니다.

## ⚙️ 설정

`image_converter.py` 파일 상단에서 모니터링 폴더를 변경할 수 있습니다:

```python
WATCH_DIRECTORIES = [
    r"D:\Downloads",
    r"C:\Users\minsang\Downloads",
]
```

기본값으로 위 두 폴더를 모두 감시하며, 존재하지 않는 경로는 경고만 남기고 건너뜁니다.

## 🖼️ 변환 대상

| 변환 대상 | 결과 |
|-----------|------|
| `.webp`, `.heic`, `.heif`, `.avif` | `.png` |
| `.bmp`, `.tiff`, `.tif`, `.ico`, `.jxl` | `.png` |

| 클립보드만 복사 (변환 안 함) |
|------------------------------|
| `.png`, `.jpg`, `.jpeg`, `.gif` |

## 🔧 시스템 트레이

실행 후 시스템 트레이에 아이콘이 나타납니다:

- 🟢 녹색 = 활성 상태
- 🔴 빨간색 = 일시정지 상태

**우클릭 메뉴:**
- ⏸️ 일시정지 / ▶️ 재개
- ❌ 종료

## 🔁 자동 시작

현재 사용자 로그인 시 자동으로 백그라운드 실행되도록 설정할 수 있습니다:

```bash
enable_autostart.bat
```

해제:

```bash
disable_autostart.bat
```

## 📋 요구사항

- Windows
- Python 3.10+
- 패키지: `watchdog`, `Pillow`, `pillow-heif`, `pywin32`, `pystray`

## 📄 라이선스

MIT License
