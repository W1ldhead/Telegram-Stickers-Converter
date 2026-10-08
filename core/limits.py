"""Требования Telegram к видеостикерам и параметры подгонки (раздел ТЗ «Требования Telegram»)."""

SIDE = 512                    # большая сторона кадра, px
MAX_DURATION = 3.0            # предел Telegram, с
TARGET_DURATION = 2.95        # итог с запасом на округление в метаданных, с
MAX_FPS = 30
MAX_BYTES = 256 * 1024        # 262 144 байта — предел Telegram
TARGET_BYTES = 260_000        # целевой размер с запасом

CRF_MIN = 15                  # лучшее качество
CRF_MAX = 63                  # худшее качество
CRF_FIRST = 30                # первая проба
FALLBACK_FPS = (24, 20)       # если не влезает даже CRF 63

INPUT_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".gif")
OUTPUT_SUFFIX = "_sticker"
