"""Decision quality evaluation - evaluates decision quality independent of outcome.

This module implements the core post-mortem principle:
"屏蔽结果，只看决策" (Hide results, only look at decisions)

The four-quadrant classification:
🟢 DESERVED_WIN: Good decision + Profit (应得的成功)
🟡 BAD_LUCK: Good decision + Loss (坏运气，不改策略)
🔴 DANGEROUS_WIN: Bad decision + Profit (危险的成功，必须警惕)
⚫ DESERVED_LOSS: Bad decision + Loss (该亏的，找出漏洞)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .trade_recorder import TradeRecord, DecisionSnapshot


class OutcomeClassification(str, Enum):
    """Four-quadrant outcome classification."""
    DESERVED_WIN = "DESERVED_WIN"      # 🟢 Good decision + Profit
    BAD_LUCK = "BAD_LUCK"              # 🟡 Good decision + Loss
    DANGEROUS_WIN = "DANGEROUS_WIN"    # 🔴 Bad decision + Profit
    DESERVED_LOSS = "DESERVED_LOSS"    # ⚫ Bad decision + Loss


@dataclass
class DecisionQualityScores:
    """Individual dimension scores for decision quality."""
    # 信息充分度：当时掌握的信息是否足够？
    information_completeness: float = 0.0
    # 逻辑严密度：推理过程是否有漏洞？
    logic_rigor: float = 0.0
    # 系统符合度：是否严格按策略执行？
    system_compliance: float = 0.0
    # 仓位合理度：凯利计算是否正确？
    position_rationality: float = 0.0
    # 综合决策质量分
    overall: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "information_completeness": self.information_completeness,
            "logic_rigor": self.logic_rigor,
            "system_compliance": self.system_compliance,
            "position_rationality": self.position_rationality,
            "overall": self.overall,
        }


@dataclass
class EvaluationReport:
    """Complete decision evaluation report."""
    trade_id: str
    scores: DecisionQualityScores
    classification: Optional[OutcomeClassification] = None
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "scores": self.scores.to_dict(),
            "classification": self.classification.value if self.classification else None,
            "issues": self.issues,
            "recommendations": self.recommendations,
        }


class DecisionQualityEvaluator:
    """Evaluator for decision quality - independent of outcome.

    This evaluator focuses on the quality of the decision process,
    not on whether the trade was profitable.
    """

    # Thresholds for quality evaluation
    GOOD_DECISION_THRESHOLD = 0.7
    ACCEPTABLE_DECISION_THRESHOLD = 0.5

    def __init__(
        self,
        min_required_vars: int = 3,
        required_signal_fields: Optional[list[str]] = None,
        required_risk_fields: Optional[list[str]] = None,
    ) -> None:
        """Initialize the evaluator with configuration.

        Args:
            min_required_vars: Minimum number of variables expected in snapshot
            required_signal_fields: Signal fields that should be present
            required_risk_fields: Risk check fields that should be present
        """
        self._min_required_vars = min_required_vars
        self._required_signal_fields = required_signal_fields or [
            "opportunity_score",
        ]
        self._required_risk_fields = required_risk_fields or [
            "can_trade",
        ]

    def evaluate(
        self,
        record: TradeRecord,
        hide_result: bool = True
    ) -> EvaluationReport:
        """Evaluate decision quality for a trade record.

        Args:
            record: The trade record to evaluate
            hide_result: If True, don't classify outcome (pure decision evaluation)

        Returns:
            EvaluationReport with scores, classification, and recommendations
        """
        issues: list[str] = []
        recommendations: list[str] = []
        snapshot = record.decision_snapshot

        # Evaluate each dimension
        info_score = self._eval_info_completeness(snapshot, issues, recommendations)
        logic_score = self._eval_logic_rigor(snapshot, issues, recommendations)
        compliance_score = self._eval_system_compliance(snapshot, issues, recommendations)
        position_score = self._eval_position_rationality(snapshot, issues, recommendations)

        # Calculate overall score
        overall = (info_score + logic_score + compliance_score + position_score) / 4.0

        scores = DecisionQualityScores(
            information_completeness=info_score,
            logic_rigor=logic_score,
            system_compliance=compliance_score,
            position_rationality=position_score,
            overall=overall,
        )

        # Classify outcome if not hidden and outcome data is available
        classification = None
        if not hide_result and record.pnl is not None:
            classification = self.classify_outcome(scores.overall, record.pnl)

        return EvaluationReport(
            trade_id=record.trade_id,
            scores=scores,
            classification=classification,
            issues=issues,
            recommendations=recommendations,
        )

    def classify_outcome(
        self,
        decision_quality: float,
        pnl: float
    ) -> OutcomeClassification:
        """Classify the outcome into four quadrants.

        Args:
            decision_quality: Overall decision quality score (0-1)
            pnl: Profit/loss amount

        Returns:
            OutcomeClassification enum value
        """
        is_good_decision = decision_quality >= self.GOOD_DECISION_THRESHOLD
        is_profit = pnl > 0

        if is_good_decision:
            return OutcomeClassification.DESERVED_WIN if is_profit else OutcomeClassification.BAD_LUCK
        else:
            return OutcomeClassification.DANGEROUS_WIN if is_profit else OutcomeClassification.DESERVED_LOSS

    def _eval_info_completeness(
        self,
        snapshot: DecisionSnapshot,
        issues: list[str],
        recommendations: list[str],
    ) -> float:
        """Evaluate if sufficient information was available at decision time."""
        score = 1.0
        penalties = 0

        # Check market variables
        if not snapshot.market_vars:
            score -= 0.3
            penalties += 1
            issues.append("No market variables recorded at decision time")
            recommendations.append("Ensure market variables are captured before trading")
        elif len(snapshot.market_vars) < self._min_required_vars:
            score -= 0.15
            penalties += 1
            issues.append(f"Only {len(snapshot.market_vars)} market vars, expected >= {self._min_required_vars}")

        # Check stock variables
        if not snapshot.stock_vars:
            score -= 0.3
            penalties += 1
            issues.append("No stock variables recorded at decision time")
            recommendations.append("Ensure stock variables are captured before trading")
        elif len(snapshot.stock_vars) < self._min_required_vars:
            score -= 0.15
            penalties += 1
            issues.append(f"Only {len(snapshot.stock_vars)} stock vars, expected >= {self._min_required_vars}")

        # Check signal snapshot
        if not snapshot.signal_snapshot:
            score -= 0.2
            penalties += 1
            issues.append("No signal snapshot recorded")
        else:
            missing_signals = [
                f for f in self._required_signal_fields
                if f not in snapshot.signal_snapshot
            ]
            if missing_signals:
                score -= 0.1 * len(missing_signals)
                issues.append(f"Missing signal fields: {missing_signals}")

        return max(0.0, score)

    def _eval_logic_rigor(
        self,
        snapshot: DecisionSnapshot,
        issues: list[str],
        recommendations: list[str],
    ) -> float:
        """Evaluate if the reasoning process was sound."""
        score = 1.0

        # Check if regime state was considered
        if not snapshot.regime_state:
            score -= 0.25
            issues.append("Regime state not recorded")
            recommendations.append("Always record market regime before trading")

        # Check if strategy was identified
        if not snapshot.strategy_triggered:
            score -= 0.25
            issues.append("No strategy identified for this trade")
            recommendations.append("Each trade should be attributed to a specific strategy")

        # Check signal score consistency with regime
        signal = snapshot.signal_snapshot
        regime = snapshot.regime_state

        if signal and regime:
            opportunity_score = signal.get("opportunity_score", 0)
            # In BEAR regime, high opportunity scores are suspicious
            if regime == "BEAR" and opportunity_score > 80:
                score -= 0.2
                issues.append(f"High opportunity score ({opportunity_score}) in BEAR regime - verify logic")
            # In TRANSITION regime, any trade is risky
            if regime == "TRANSITION":
                score -= 0.3
                issues.append("Trading during TRANSITION regime violates system rules")
                recommendations.append("Avoid new positions during regime transitions")

        return max(0.0, score)

    def _eval_system_compliance(
        self,
        snapshot: DecisionSnapshot,
        issues: list[str],
        recommendations: list[str],
    ) -> float:
        """Evaluate if the trade followed system rules."""
        score = 1.0

        # Check risk check result
        risk_result = snapshot.risk_check_result
        if not risk_result:
            score -= 0.4
            issues.append("No risk check result recorded")
            recommendations.append("All trades must pass risk review before execution")
            return max(0.0, score)

        # Check if trade was approved
        if not risk_result.get("can_trade", False):
            score -= 0.5
            issues.append("Trade executed despite risk rejection")
            recommendations.append("CRITICAL: Review execution layer - rejected trades should not execute")

        # Check for required risk fields
        missing_risk = [
            f for f in self._required_risk_fields
            if f not in risk_result
        ]
        if missing_risk:
            score -= 0.1 * len(missing_risk)
            issues.append(f"Missing risk check fields: {missing_risk}")

        return max(0.0, score)

    def _eval_position_rationality(
        self,
        snapshot: DecisionSnapshot,
        issues: list[str],
        recommendations: list[str],
    ) -> float:
        """Evaluate if position sizing was rational (Kelly criterion)."""
        score = 1.0

        kelly = snapshot.kelly_calculation
        if not kelly:
            score -= 0.3
            issues.append("No Kelly calculation recorded")
            recommendations.append("Document Kelly calculation for all trades")
            return max(0.0, score)

        # Check if Kelly fraction was applied
        f_star = kelly.get("f_star", 0)
        conservative_factor = kelly.get("conservative_factor", 1.0)

        if f_star <= 0:
            score -= 0.3
            issues.append(f"Negative or zero Kelly fraction ({f_star}) - trade should not have been taken")
            recommendations.append("Only trade when Kelly criterion shows positive edge")

        if f_star > 0.25:
            score -= 0.1
            issues.append(f"Very high Kelly fraction ({f_star}) - verify edge calculation")

        if conservative_factor > 0.6:
            score -= 0.1
            issues.append(f"Conservative factor ({conservative_factor}) too aggressive - use 0.5 or less")

        return max(0.0, score)


class DecisionEvaluatorService:
    """Service for batch evaluation and reporting."""

    def __init__(self, evaluator: Optional[DecisionQualityEvaluator] = None) -> None:
        self._evaluator = evaluator or DecisionQualityEvaluator()

    def evaluate_batch(
        self,
        records: list[TradeRecord],
        hide_results: bool = True,
    ) -> list[EvaluationReport]:
        """Evaluate multiple trade records."""
        return [self._evaluator.evaluate(r, hide_results) for r in records]

    def generate_summary(
        self,
        reports: list[EvaluationReport],
    ) -> dict[str, Any]:
        """Generate summary statistics from evaluation reports."""
        if not reports:
            return {"count": 0}

        total = len(reports)
        avg_overall = sum(r.scores.overall for r in reports) / total

        # Count by classification
        classifications = {}
        for r in reports:
            if r.classification:
                cls = r.classification.value
                classifications[cls] = classifications.get(cls, 0) + 1

        # Collect common issues
        issue_counts: dict[str, int] = {}
        for r in reports:
            for issue in r.issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

        top_issues = sorted(issue_counts.items(), key=lambda x: -x[1])[:5]

        return {
            "count": total,
            "average_quality": round(avg_overall, 3),
            "classifications": classifications,
            "top_issues": top_issues,
            "good_decisions_pct": round(
                sum(1 for r in reports if r.scores.overall >= 0.7) / total * 100, 1
            ),
        }
