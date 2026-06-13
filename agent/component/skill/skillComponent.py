"""SkillComponent —— 将 Skill 管理封装为可挂载的 IComponent。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(SkillComponent) 获取
Skill 注册表，支持渐进式披露（Layer 1 前缀注入 + Layer 2 按需加载）。
对标 Claude Code SKILL.md 的渐进式披露架构。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from agent.core.baseComponent import IComponent

from .skill import Skill
from .skillLoader import SkillLoader

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class SkillComponent(IComponent):
    """Skill 管理组件 —— 持有 Skill 注册表与文件加载器。

    挂载到 BaseAgent 后自动可用，通过 GetComponent(SkillComponent) 获取。
    对标 Claude Code 的 Skill 管理机制：
    - Layer 1: GetAllPrefixes() 返回 name+description 清单，注入 system prompt。
    - Layer 2: LoadSkill() 按名称返回完整正文，作为 Tool Result 注入 context。

    用法::

        agent = BaseAgent()
        skillComp = SkillComponent()
        agent.AddComponent(skillComp)
        skillComp.LoadFromDirectory(".claude/skills")
        prefixes = skillComp.GetAllPrefixes()
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._loader = SkillLoader()

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，清空所有已注册 Skill。"""
        self._skills.clear()
        self._loader.Clear()

    # ---- 注册 ----

    def Register(self, skill: Skill) -> None:
        """注册一个 Skill（同名覆盖）。"""
        if not skill.name:
            raise ValueError("Skill must have a non-empty name")
        self._skills[skill.name] = skill

    def Unregister(self, name: str) -> None:
        """移除指定 Skill。"""
        self._skills.pop(name, None)

    # ---- 查询 ----

    def Get(self, name: str) -> Skill | None:
        """按名称获取 Skill。"""
        return self._skills.get(name)

    def GetAll(self) -> dict[str, Skill]:
        """获取所有已注册 Skill 的副本。"""
        return dict(self._skills)

    def GetAutoInvokable(self) -> list[Skill]:
        """获取所有允许 Agent 自动调用的 Skill。"""
        return [s for s in self._skills.values() if s.IsAutoInvokable()]

    # ---- 文件系统加载 ----

    def LoadFromDirectory(self, directory: str) -> int:
        """从目录加载所有 SKILL.md 文件。

        Args:
            directory: skills 根目录路径。

        Returns:
            成功加载的 Skill 数量。
        """
        self._loader.Clear()
        count = self._loader.ScanDirectory(directory)
        for skill in self._loader.GetAllSkills().values():
            self.Register(skill)
        return count

    def LoadSingleFile(self, filePath: str) -> Skill | None:
        """加载单个 SKILL.md 文件并注册。

        Args:
            filePath: SKILL.md 文件路径。

        Returns:
            解析后的 Skill 对象，失败返回 None。
        """
        skill = self._loader.LoadSingleFile(filePath)
        if skill:
            self.Register(skill)
        return skill

    # ---- 渐进式披露接口 ----

    def GetAllPrefixes(self) -> str:
        """Layer 1: 获取所有 Skill 的 name + description 清单。

        用于注入 system prompt，每条约 100 tokens。
        Agent 据此判断哪个 Skill 与当前任务相关。
        """
        if not self._skills:
            return "No skills available."
        lines = [skill.GetPrefix() for skill in self._skills.values()]
        return "\n".join(lines)

    def LoadSkill(self, name: str) -> str:
        """Layer 2: 按名称加载 Skill 的完整正文。

        这是 load_skill 工具的核心回调函数。
        对标 Claude Code 的 tool_result 注入机制。

        Args:
            name: Skill 名称。

        Returns:
            Skill 的完整 SOP 正文（带 ``<skill>`` 标签包裹），找不到时返回错误信息。
        """
        skill = self._skills.get(name)
        if not skill:
            available = ", ".join(sorted(self._skills.keys()))
            return f"Error: Unknown skill '{name}'. Available: {available}"
        return skill.GetContent()

    # ---- load_skill 工具定义 ----

    def GetLoadSkillHandlers(self) -> dict[str, Callable[..., str]]:
        """返回绑定当前组件的 load_skill 工具回调。"""
        return {"load_skill": lambda **kw: self.LoadSkill(kw["name"])}

    @staticmethod
    def GetToolDefinition() -> dict[str, Any]:
        """获取 load_skill 工具的 Function Calling 定义。

        可直接注入 LLM 的 tools 列表中。

        Returns:
            OpenAI/Anthropic 兼容的 tool 定义字典。
        """
        return {
            "type": "function",
            "function": {
                "name": "load_skill",
                "description": (
                    "Load a skill's full instructions by name. "
                    "Call this when a skill's description suggests it is relevant "
                    "to the current task. Returns the skill's complete SOP."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The name of the skill to load.",
                        },
                    },
                    "required": ["name"],
                },
            },
        }

    # ---- 管理 ----

    def Count(self) -> int:
        """已注册 Skill 总数。"""
        return len(self._skills)

    def Clear(self) -> None:
        """清空所有注册（谨慎使用）。"""
        self._skills.clear()
        self._loader.Clear()

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"SkillComponent(skills={len(self._skills)})"

    def __contains__(self, name: str) -> bool:
        return name in self._skills
