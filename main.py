#!/usr/bin/env python3
"""Complaint Auto-Adjudication System — Main Entry Point.

私域社群「无效投诉自动裁断」Agent
=====================================
A 5-agent pipeline for automated complaint handling in private community channels
(WeChat, Discord, etc.).

Usage:
    python main.py                        # Interactive demo mode
    python main.py --message "投诉文本"    # Single complaint processing
    python main.py --audit               # Run weekly confidence audit
    python main.py --stats               # Show system statistics
    python main.py --demo                # Run demo with 6 test scenarios
"""

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import config, Config
from core.orchestrator import ComplaintOrchestrator
from models.complaint import ComplaintSource
from utils.logger import setup_logger


console = Console()

# Demo scenarios covering all categories
DEMO_SCENARIOS = [
    {
        "user_id": "user_a_001",
        "message": "你们这个春节活动我明明点了领取按钮，皮肤到现在都没收到！都等了好几天了，客服也没人理我，到底什么时候能发？",
        "description": "场景1: 活动奖励未到账（应支持补发）",
        "expected": "support",
        "human_label": "support",
    },
    {
        "user_id": "user_b_002",
        "message": "春节活动不是说登录就能领皮肤吗？我活动期间天天在线，为什么没收到皮肤？",
        "description": "场景2: 未点击领取（应驳回）",
        "expected": "reject",
        "human_label": "reject",
    },
    {
        "user_id": "user_d_004",
        "message": "凭什么封我的号？！我什么都没做就被封了，你们系统是不是有问题？赶紧给我解封！",
        "description": "场景3: 作弊封号申诉（应驳回）",
        "expected": "reject",
        "human_label": "reject",
    },
    {
        "user_id": "user_e_005",
        "message": "我就发了个链接就被封了7天，这也太不合理了吧？能不能提前解封？",
        "description": "场景4: 广告引流封禁（应驳回）",
        "expected": "reject",
        "human_label": "reject",
    },
    {
        "user_id": "user_x_999",
        "message": "你们这个辣鸡游戏，Bug一堆，充钱也不给东西，客服全是机器人，我要去12315投诉你们！",
        "description": "场景5: 情绪化发泄（应过滤）",
        "expected": "not_complaint",
        "human_label": "not_complaint",
    },
    {
        "user_id": "user_y_888",
        "message": "你好，我想问一下这周的维护时间是几点？",
        "description": "场景6: 普通咨询（应过滤）",
        "expected": "not_complaint",
        "human_label": "not_complaint",
    },
]

# Additional complex scenario
COMPLEX_SCENARIO = {
    "user_id": "user_z_777",
    "message": (
        "我参加了3周年庆典活动，累计登录了8天但是头像框没领到。"
        "我确定我登录满了的，你们查一下记录吧。"
    ),
    "description": "场景7: 周年庆活动（复杂推理 — 需检查ANNIVERSARY活动数据）",
    "expected": "human_review",
    "human_label": "support",
}


def print_banner():
    console.print(Panel(
        Text("私域社群「无效投诉自动裁断」Agent\n"
             "Multi-Agent Complaint Auto-Adjudication System",
             style="bold cyan", justify="center"),
        border_style="cyan",
    ))


def print_result(result):
    """Pretty-print a pipeline result."""
    arb = result.arbitration

    verdict_style = {
        "support": "green",
        "reject": "red",
        "human_review": "yellow",
    }.get(arb.verdict.value, "white")

    # Timing table
    timing_table = Table(title="Agent 耗时")
    timing_table.add_column("Agent", style="cyan")
    timing_table.add_column("耗时 (ms)", style="yellow", justify="right")
    timing_table.add_column("占比", style="dim", justify="right")

    total = sum(result.agent_timings.values())
    for agent, ms in result.agent_timings.items():
        pct = f"{ms / total * 100:.0f}%" if total > 0 else "-"
        timing_table.add_row(agent, f"{ms:.0f}", pct)
    timing_table.add_row("[bold]总计[/bold]", f"[bold]{result.total_time_ms:.0f}[/bold]", "100%")

    console.print(timing_table)

    # Verdict panel
    console.print(Panel(
        arb.to_report(),
        title=f"[bold {verdict_style}]裁决结果: {arb.verdict.value.upper()}[/bold {verdict_style}]",
        border_style=verdict_style,
    ))

    if result.errors:
        console.print(f"[red]错误: {result.errors}[/red]")


def run_demo(orchestrator: ComplaintOrchestrator):
    """Run through all demo scenarios."""
    print_banner()
    console.print("\n[bold]运行 7 个测试场景...[/bold]\n")

    all_scenarios = DEMO_SCENARIOS + [COMPLEX_SCENARIO]
    results = []

    for i, scenario in enumerate(all_scenarios, 1):
        console.rule(f"[bold yellow]{scenario['description']}")
        console.print(f"[dim]用户: {scenario['user_id']}[/dim]")
        console.print(f"[dim]消息: {scenario['message'][:100]}...[/dim]")
        console.print(f"[dim]预期: {scenario['expected']}[/dim]")
        console.print()

        result = orchestrator.process(
            scenario["message"],
            user_id=scenario["user_id"],
            source=ComplaintSource.WECHAT,
        )

        # Submit human label for confidence loop
        orchestrator.submit_human_label(
            result.complaint.id, scenario["human_label"])

        print_result(result)
        results.append(result)

        if i < len(all_scenarios):
            console.print()

    # Summary table
    summary_table = Table(title="\n测试场景汇总")
    summary_table.add_column("#", style="dim")
    summary_table.add_column("场景")
    summary_table.add_column("预期")
    summary_table.add_column("实际")
    summary_table.add_column("置信度")
    summary_table.add_column("耗时")
    summary_table.add_column("匹配")

    correct = 0
    for i, (scenario, result) in enumerate(zip(all_scenarios, results), 1):
        actual = result.arbitration.verdict.value
        expected = scenario["expected"]
        matched = actual == expected or (
            expected == "not_complaint" and not result.complaint.is_adjudicable
        )
        if matched:
            correct += 1
        match_icon = "✅" if matched else "❌"
        summary_table.add_row(
            str(i),
            scenario["description"][:30],
            expected,
            f"[{match_icon}] {actual}",
            f"{result.arbitration.confidence:.0%}",
            f"{result.total_time_ms:.0f}ms",
            match_icon,
        )

    console.print(summary_table)
    console.print(f"\n[bold]准确率: {correct}/{len(all_scenarios)} ({correct/len(all_scenarios):.0%})[/bold]")

    # Run confidence audit
    console.print("\n[bold cyan]运行置信度审计...[/bold cyan]")
    audit = orchestrator.run_weekly_confidence_audit()
    console.print(f"  一致率: {audit.agreement_rate:.1%}")
    console.print(f"  一致样本: {audit.agreement_count}/{audit.sample_size}")
    if audit.rules_update_triggered:
        console.print(f"  [red]⚠ 一致率低于90%阈值，触发规则更新提示[/red]")
        for update in audit.suggested_rule_updates:
            console.print(f"    - 规则 {update.get('rule_id')}: {update.get('current_issue')}")
    else:
        console.print("  [green]✓ 一致率达标[/green]")


def run_interactive(orchestrator: ComplaintOrchestrator):
    """Interactive mode — user types complaints and sees results."""
    print_banner()
    console.print("\n[dim]输入投诉消息，系统将自动裁断。输入 'quit' 退出，输入 'stats' 查看统计。[/dim]\n")

    while True:
        try:
            message = console.input("[bold green]投诉消息> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        if message.lower() in ("quit", "exit", "q"):
            break
        elif message.lower() == "stats":
            stats = orchestrator.get_stats()
            console.print(stats)
            continue
        elif message.lower() == "audit":
            audit = orchestrator.run_weekly_confidence_audit()
            console.print(f"一致率: {audit.agreement_rate:.1%}")
            continue

        if not message.strip():
            continue

        result = orchestrator.process(message)
        print_result(result)

        # Ask for human label for confidence loop
        if result.complaint.is_adjudicable:
            console.print("[dim]请标注正确的裁决 (support/reject/human_review/skip): [/dim]", end="")
            try:
                label = input().strip()
                if label in ("support", "reject", "human_review"):
                    orchestrator.submit_human_label(result.complaint.id, label)
                    console.print("[dim]已记录标注[/dim]")
            except (EOFError, KeyboardInterrupt):
                pass


def main():
    parser = argparse.ArgumentParser(
        description="私域社群「无效投诉自动裁断」Agent")
    parser.add_argument("--message", "-m", type=str, help="单条投诉消息")
    parser.add_argument("--user-id", "-u", type=str, default="",
                        help="用户ID（可选）")
    parser.add_argument("--demo", action="store_true",
                        help="运行全部7个演示场景")
    parser.add_argument("--audit", action="store_true",
                        help="运行置信度审计")
    parser.add_argument("--stats", action="store_true",
                        help="显示系统统计")
    parser.add_argument("--model", type=str, default=None,
                        help=f"模型名称 (默认: {config.default_model})")
    args = parser.parse_args()

    # Setup logging
    setup_logger(level=config.log_level, log_file=config.log_file)

    # Initialize orchestrator
    orch = ComplaintOrchestrator(model=args.model)

    if args.demo:
        run_demo(orch)
    elif args.audit:
        print_banner()
        report = orch.run_weekly_confidence_audit()
        console.print(f"置信度审计完成 | 一致率: {report.agreement_rate:.1%}")
    elif args.stats:
        print_banner()
        stats = orch.get_stats()
        console.print(stats)
    elif args.message:
        print_banner()
        result = orch.process(args.message, user_id=args.user_id)
        print_result(result)
    else:
        run_interactive(orch)


if __name__ == "__main__":
    main()
