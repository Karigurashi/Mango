"""ContextAssembler 与 Memory 集成验证。"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest

from agent.contex import ContextEngine, EContextLodLevel, Session
from agent.contex.subagentContext import ESubagentContextMode, SubagentContext
from agent.extension.rule import ERuleTriggerMode, Rule, RuleRegistry
from agent.harness import ContextAssembler
from agent.memory import FileMemory
from common.const import ERole


class TestContextAssembler(unittest.IsolatedAsyncioTestCase):
    async def test_build_ingests_system_blocks(self) -> None:
        ruleRegistry = RuleRegistry()
        ruleRegistry.Register(
            Rule(
                name="test-always",
                triggerMode=ERuleTriggerMode.ALWAYS_APPLY,
                body="Always apply this rule.",
            )
        )

        tmp = tempfile.mkdtemp()
        try:
            mem = FileMemory(tmp)
            mem.SaveContextBlocks(["[Previous session] User prefers concise answers."])

            session = Session()
            session.LoadFromMemory(mem)
            engine = ContextEngine(session)
            assembler = ContextAssembler(
                baseSystemPrompt="You are Brain Agent.",
                ruleRegistry=ruleRegistry,
            )
            count = await assembler.BuildAsync(engine)

            self.assertGreaterEqual(count, 3)
            msgs = await engine.AssembleAsync()
            self.assertTrue(all(m.lodLevel == EContextLodLevel.RESIDENT for m in msgs))
            contents = " ".join(m.content for m in msgs)
            self.assertIn("Brain Agent", contents)
            self.assertIn("Always apply this rule", contents)
            self.assertIn("Previous session", contents)
            self.assertIn("<environment>", contents)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def test_lod3_tool_result_externalized(self) -> None:
        session = Session()
        engine = ContextEngine(session)
        big = "x\n" * 600
        engine.Ingest(ERole.TOOL, big, metadata={"toolName": "read_file"})
        toolMsg = session.GetAll()[0]
        self.assertTrue(toolMsg.metadata.get("externalOnly"))
        assembled = await engine.AssembleAsync()
        self.assertEqual(len(assembled), 1)

    async def test_subagent_fork_and_merge(self) -> None:
        parent = Session()
        pe = ContextEngine(parent)
        pe.Ingest(ERole.SYSTEM, "system prompt", metadata={"isContextBlock": True})
        pe.Ingest(ERole.USER, "hello")
        pe.Ingest(ERole.ASSISTANT, "hi", metadata={"isDecision": True})

        sub = SubagentContext()
        child = await sub.PrepareSpawnAsync(parent, ESubagentContextMode.FORK)
        self.assertEqual(len(child.GetAll()), 3)

        ce = ContextEngine(child)
        ce.Ingest(ERole.ASSISTANT, "child result", metadata={"isDecision": True})
        await sub.EndSubagentAsync(child, parent)
        self.assertEqual(len(parent.GetAll()), 4)
        self.assertTrue(any(m.metadata.get("fromSubagent") for m in parent.GetAll()))

    async def test_save_to_memory(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            mem = FileMemory(tmp)
            session = Session()
            session.LoadFromMemory(mem)
            engine = ContextEngine(session)
            engine.Ingest(ERole.USER, "q")
            engine.Ingest(ERole.ASSISTANT, "final answer from agent")
            session.SaveToMemory()
            saved = mem.LoadSessionSummary(session.sessionId)
            self.assertEqual(saved, "final answer from agent")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
