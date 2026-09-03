"""依次运行 MDS pandas 教程的全部课程。"""

from __future__ import annotations

from collections.abc import Callable

from .pandas_01_io_selection import main as lesson_01_main
from .pandas_02_snapshot_groupby import main as lesson_02_main
from .pandas_03_aggregate_merge import main as lesson_03_main
from .pandas_04_time_large_data import main as lesson_04_main
from .pandas_05_csv_files import main as lesson_05_main

LESSONS: tuple[tuple[str, Callable[[], int]], ...] = (
    ("第一课：CSV、类型与筛选", lesson_01_main),
    ("第二课：snapshot 与 groupby", lesson_02_main),
    ("第三课：聚合、配对与 merge", lesson_03_main),
    ("第四课：时间切片与大文件", lesson_04_main),
    ("第五课：创建、合并与追加 CSV", lesson_05_main),
)


def main() -> int:
    """按顺序运行全部课程；任一课程失败时返回其退出码。"""

    for number, (title, lesson_main) in enumerate(LESSONS, start=1):
        print("\n" + "=" * 72)
        print(f"{number}. {title}")
        print("=" * 72)
        exit_code = lesson_main()
        if exit_code != 0:
            return exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
