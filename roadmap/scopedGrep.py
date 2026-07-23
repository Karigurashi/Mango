"""范围内 grep —— 仅在模块 roots 内搜索（ripgrep）。"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class GrepResult:
    """grep 执行结果。"""

    ok: bool
    command: list[str]
    output: str
    returnCode: int


class ScopedGrep:
    """在给定 roots 内调用 rg。"""

    def __init__(self, rgPath: str | None = None) -> None:
        self._rgPath = rgPath or shutil.which("rg")

    @property
    def available(self) -> bool:
        return bool(self._rgPath)

    def Search(
        self,
        pattern: str,
        roots: list[str],
        glob: str = "*.cs",
        caseInsensitive: bool = True,
        maxCount: int = 20,
        context: int = 0,
    ) -> GrepResult:
        if not self._rgPath:
            return GrepResult(
                ok=False,
                command=[],
                output=(
                    "ripgrep (rg) not found in PATH. "
                    "Install: winget install BurntSushi.ripgrep.MSVC"
                ),
                returnCode=127,
            )
        if not roots:
            return GrepResult(
                ok=False,
                command=[],
                output="No search roots. Resolve a module first.",
                returnCode=2,
            )

        existing = [r for r in roots if os.path.exists(r)]
        if not existing:
            return GrepResult(
                ok=False,
                command=[],
                output="All module roots are missing on disk.",
                returnCode=2,
            )

        cmd = [
            self._rgPath,
            "--line-number",
            "--with-filename",
            "--color",
            "never",
            f"--max-count={maxCount}",
        ]
        if caseInsensitive:
            cmd.append("--ignore-case")
        if context > 0:
            cmd.extend(["--context", str(context)])
        if glob:
            cmd.extend(["--glob", glob])
        # Unity / 常见噪音
        for g in (
            "!**/Library/**",
            "!**/Temp/**",
            "!**/Obj/**",
            "!**/bin/**",
            "!**/Logs/**",
            "!**/.git/**",
        ):
            cmd.extend(["--glob", g])

        cmd.append("--")
        cmd.append(pattern)
        cmd.extend(existing)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as ex:
            return GrepResult(ok=False, command=cmd, output=str(ex), returnCode=1)

        text = proc.stdout
        if proc.returncode not in (0, 1):
            err = (proc.stderr or "").strip()
            text = err or text
            return GrepResult(ok=False, command=cmd, output=text, returnCode=proc.returncode)

        if proc.returncode == 1 and not text.strip():
            text = "(no matches)"
        return GrepResult(ok=True, command=cmd, output=text.rstrip() + "\n", returnCode=proc.returncode)
