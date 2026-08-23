# -*- coding: utf-8 -*-
"""
蜗牛AI Business Opportunity Scan — 报告 HTML 模板
===================================================
将验证后的 JSON 分析渲染为完整 HTML 报告
"""


def render_report_html(analysis: dict, norm: dict, scoring: dict, submission: dict) -> str:
    """渲染完整报告 HTML"""
    biz = norm["business"]
    industry = norm["industry"]
    pain = norm["pain"]
    readiness = norm["readiness"]
    tools = norm["tools"]

    # Lead Fit 显示名（不直接暴露销售评分）
    readiness_label = {
        "high": "High Opportunity Readiness",
        "potential": "Moderate Opportunity Readiness",
        "early": "Early Stage — Foundations Building",
        "low": "Exploring AI Potential",
    }.get(scoring["lead_fit_band"], "Under Assessment")

    # Next Step CTA
    if scoring["lead_fit_band"] == "high":
        next_cta = "Apply for a 20-minute validation call"
        next_desc = "You may also be eligible for a complimentary two-hour on-site AI Opportunity Assessment with Robin."
    elif scoring["lead_fit_band"] == "potential":
        next_cta = "Discuss your result with Snail AI"
        next_desc = "A short conversation can help clarify which opportunities to pursue first."
    elif scoring["lead_fit_band"] == "early":
        next_cta = "Join a Business Owner AI Workflow Workshop"
        next_desc = "Learn practical AI workflow patterns alongside other business owners."
    else:
        next_cta = "Download the practical AI starter guide"
        next_desc = "Start exploring AI possibilities at your own pace."

    # 现场评估资格
    onsite_note = ""
    if scoring.get("onsite_eligible"):
        onsite_note = """
        <div class="onsite-eligibility">
            <h3>On-Site Assessment Available</h3>
            <p>Based on your responses, your business may be eligible for a complimentary two-hour on-site AI Opportunity Assessment with Robin at your Sydney workplace.</p>
            <p><em>Eligibility is preliminary. Final confirmation and scheduling are at Robin's discretion.</em></p>
        </div>
        """

    # 机会卡片
    opportunity_cards = ""
    for opp in analysis.get("top_opportunities", []):
        impact_color = {"high": "#16a34a", "medium": "#d97706", "low": "#6b7280"}.get(opp.get("impact", "low"), "#6b7280")
        effort_color = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}.get(opp.get("effort", "low"), "#6b7280")
        risk_color = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}.get(opp.get("risk", "low"), "#6b7280")

        opportunity_cards += f"""
        <div class="opportunity-card">
            <div class="opp-header">
                <span class="opp-rank">#{opp.get('rank', '?')}</span>
                <h3>{_e(opp.get('title', ''))}</h3>
                <span class="opp-score">{opp.get('opportunity_score', 0)}/100</span>
            </div>
            <div class="opp-body">
                <div class="opp-section">
                    <h4>Current Problem</h4>
                    <p>{_e(opp.get('problem', ''))}</p>
                </div>
                <div class="opp-section">
                    <h4>Recommended Workflow</h4>
                    <p>{_e(opp.get('recommended_workflow', ''))}</p>
                </div>
                <div class="opp-section">
                    <h4>Human Approval Point</h4>
                    <p class="approval-point">{_e(opp.get('human_approval', ''))}</p>
                </div>
                <div class="opp-section">
                    <h4>Systems Involved</h4>
                    <p>{_e(', '.join(opp.get('systems_involved', [])))}</p>
                </div>
                <div class="opp-badges">
                    <span class="badge" style="background:{impact_color}">Impact: {opp.get('impact', '?')}</span>
                    <span class="badge" style="background:{effort_color}">Effort: {opp.get('effort', '?')}</span>
                    <span class="badge" style="background:{risk_color}">Risk: {opp.get('risk', '?')}</span>
                </div>
                {f'<div class="opp-section"><h4>Estimated Time Impact</h4><p>{_e(opp["estimated_time_range"])}</p></div>' if opp.get("estimated_time_range") else ''}
                <div class="opp-section">
                    <h4>Assumptions</h4>
                    <ul>{''.join(f'<li>{_e(a)}</li>' for a in opp.get('assumptions', []))}</ul>
                </div>
                <div class="opp-section">
                    <h4>Success Metrics</h4>
                    <ul>{''.join(f'<li>{_e(m)}</li>' for m in opp.get('success_metrics', []))}</ul>
                </div>
            </div>
        </div>
        """

    # What Not to Automate
    not_recommended = ""
    for item in analysis.get("not_yet_recommended", []):
        not_recommended += f"""
        <div class="not-rec-item">
            <h4>{_e(item.get('title', ''))}</h4>
            <p>{_e(item.get('reason', ''))}</p>
        </div>
        """

    # Risk and Controls
    risk_controls = ""
    for rc in analysis.get("risk_and_controls", []):
        risk_controls += f"""
        <div class="risk-item">
            <div class="risk-label">{_e(rc.get('risk', ''))}</div>
            <div class="risk-control">{_e(rc.get('control', ''))}</div>
        </div>
        """

    # Pilot
    pilot = analysis.get("recommended_pilot", {})

    # 30/60/90
    path_30_60_90 = analysis.get("next_30_60_90_days", {})

    # What We Heard
    what_we_heard = f"""
    <table class="heard-table">
        <tr><td class="label">Company</td><td>{_e(biz['company_name'])}</td></tr>
        <tr><td class="label">Industry</td><td>{_e(industry['group_name'])} — {_e(industry['sub_industry'])}</td></tr>
        <tr><td class="label">Employees</td><td>{_e(biz['employee_band'])}</td></tr>
        <tr><td class="label">Location</td><td>{_e(biz['suburb'])} {_e(biz['postcode'])}</td></tr>
        <tr><td class="label">Primary Goal</td><td>{_e(biz['primary_goal'] or 'Not specified')}</td></tr>
        <tr><td class="label">Main Pain Process</td><td>{_e(pain['process'])}</td></tr>
        <tr><td class="label">Frequency</td><td>{_e(pain['frequency'])}</td></tr>
        <tr><td class="label">Weekly Hours Spent</td><td>{_e(pain['weekly_hours'])}</td></tr>
        <tr><td class="label">Current Tools</td><td>{_e(', '.join(tools['general'] + tools['industry']))}</td></tr>
        <tr><td class="label">Integration Level</td><td>{_e(tools['integration_level'])}</td></tr>
        <tr><td class="label">Data Sensitivity</td><td>{_e(readiness['data_sensitivity'])}</td></tr>
        <tr><td class="label">Start Timeline</td><td>{_e(readiness['start_timeline'])}</td></tr>
        <tr><td class="label">Budget Range</td><td>{_e(readiness['budget'])}</td></tr>
    </table>
    """

    # Questions for onsite
    questions = ""
    for q in analysis.get("questions_for_onsite", []):
        questions += f"<li>{_e(q)}</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Snail AI Business Opportunity Report — {_e(biz['company_name'])}</title>
<style>
  :root {{
    --ink: #1A1A2E;
    --ink-2: #2A2A40;
    --ink-3: #6A6A85;
    --paper: #FCFCFA;
    --paper-2: #F5F4EE;
    --accent: #FF5B1F;
    --accent-2: #E84A0F;
    --accent-light: rgba(255,91,31,0.08);
    --gold: #D4A547;
    --line: rgba(26,26,46,0.08);
    --green: #16a34a;
    --amber: #d97706;
    --red: #dc2626;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--ink); background: var(--paper); line-height: 1.6; }}
  .report {{ max-width: 800px; margin: 0 auto; padding: 40px 24px; }}

  /* Cover */
  .cover {{ text-align: center; padding: 60px 0 40px; border-bottom: 2px solid var(--accent); }}
  .cover-logo {{ width: 120px; margin-bottom: 20px; }}
  .cover h1 {{ font-size: 28px; font-weight: 800; color: var(--ink); margin-bottom: 8px; }}
  .cover .company {{ font-size: 20px; color: var(--accent); font-weight: 700; }}
  .cover .meta {{ font-size: 14px; color: var(--ink-3); margin-top: 12px; }}
  .cover .badge-prelim {{ display: inline-block; background: var(--accent-light); color: var(--accent); padding: 4px 12px; border-radius: 100px; font-size: 12px; font-weight: 600; margin-top: 12px; }}

  /* Sections */
  .section {{ margin: 40px 0; }}
  .section h2 {{ font-size: 22px; font-weight: 800; color: var(--ink); border-left: 4px solid var(--accent); padding-left: 16px; margin-bottom: 16px; }}
  .section h3 {{ font-size: 18px; font-weight: 700; color: var(--ink-2); margin-bottom: 8px; }}
  .section h4 {{ font-size: 15px; font-weight: 700; color: var(--ink-3); margin: 12px 0 4px; }}
  .section p {{ margin-bottom: 8px; }}
  .section ul {{ margin: 8px 0 8px 24px; }}

  /* Readiness Banner */
  .readiness-banner {{ background: var(--accent); color: white; padding: 16px 24px; border-radius: 12px; text-align: center; margin: 24px 0; }}
  .readiness-banner .label {{ font-size: 14px; opacity: 0.9; }}
  .readiness-banner .value {{ font-size: 24px; font-weight: 800; }}

  /* Opportunity Cards */
  .opportunity-card {{ background: var(--paper-2); border-radius: 12px; padding: 24px; margin: 16px 0; border: 1px solid var(--line); }}
  .opp-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
  .opp-rank {{ background: var(--accent); color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 14px; flex-shrink: 0; }}
  .opp-header h3 {{ flex: 1; font-size: 17px; }}
  .opp-score {{ background: var(--ink); color: white; padding: 4px 10px; border-radius: 100px; font-size: 13px; font-weight: 700; }}
  .opp-badges {{ display: flex; gap: 8px; margin: 12px 0; flex-wrap: wrap; }}
  .badge {{ color: white; padding: 4px 10px; border-radius: 100px; font-size: 12px; font-weight: 600; }}
  .approval-point {{ background: #fff3cd; border-left: 3px solid var(--amber); padding: 8px 12px; border-radius: 4px; font-size: 14px; }}

  /* Not Recommended */
  .not-rec-item {{ background: #fef2f2; border-left: 3px solid var(--red); padding: 12px 16px; margin: 8px 0; border-radius: 4px; }}

  /* Risk Items */
  .risk-item {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--line); }}
  .risk-label {{ font-weight: 600; color: var(--red); }}
  .risk-control {{ color: var(--ink-2); }}

  /* Heard Table */
  .heard-table {{ width: 100%; border-collapse: collapse; }}
  .heard-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  .heard-table .label {{ width: 160px; color: var(--ink-3); font-weight: 600; font-size: 14px; }}

  /* Pilot */
  .pilot-box {{ background: var(--accent-light); border: 1px solid var(--accent); border-radius: 12px; padding: 24px; }}

  /* Path */
  .path-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin: 16px 0; }}
  .path-card {{ background: var(--paper-2); border-radius: 8px; padding: 16px; border-top: 3px solid var(--accent); }}
  .path-card h4 {{ color: var(--accent); font-size: 14px; margin-bottom: 8px; }}

  /* CTA */
  .cta-section {{ background: var(--ink); color: white; border-radius: 12px; padding: 32px; text-align: center; margin: 32px 0; }}
  .cta-section h3 {{ font-size: 22px; margin-bottom: 12px; }}
  .cta-section p {{ opacity: 0.85; margin-bottom: 16px; }}
  .cta-button {{ display: inline-block; background: var(--accent); color: white; padding: 12px 32px; border-radius: 100px; font-weight: 700; text-decoration: none; font-size: 16px; }}

  /* On-site eligibility */
  .onsite-eligibility {{ background: #f0fdf4; border: 1px solid var(--green); border-radius: 8px; padding: 16px; margin: 16px 0; }}
  .onsite-eligibility h3 {{ color: var(--green); }}

  /* Disclaimer */
  .disclaimer {{ background: var(--paper-2); border-radius: 8px; padding: 20px; font-size: 13px; color: var(--ink-3); margin: 24px 0; }}
  .disclaimer p {{ margin-bottom: 4px; }}

  /* Print */
  @media print {{
    body {{ background: white; }}
    .report {{ padding: 20px; }}
    .cta-section {{ display: none; }}
  }}
  @media (max-width: 600px) {{
    .report {{ padding: 20px 16px; }}
    .path-grid {{ grid-template-columns: 1fr; }}
    .risk-item {{ grid-template-columns: 1fr; }}
    .heard-table .label {{ width: 120px; }}
  }}
</style>
</head>
<body>
<div class="report">

  <!-- Cover -->
  <div class="cover">
    <img src="/assets/snailai_logo.png" alt="Snail AI" class="cover-logo" onerror="this.style.display='none'">
    <h1>Business Opportunity Report</h1>
    <div class="company">{_e(biz['company_name'])}</div>
    <div class="meta">
      {_e(industry['group_name'])} — {_e(industry['sub_industry'])}<br>
      Generated {submission.get('created_at', '')[:10]}<br>
      Secure Report ID: {submission.get('id', '')[:8].upper()}
    </div>
    <span class="badge-prelim">Preliminary Assessment — Confidential</span>
  </div>

  <!-- 1. Executive Summary -->
  <div class="section">
    <h2>1. Executive Summary</h2>
    <p>{_e(analysis.get('executive_summary', ''))}</p>
    <div class="readiness-banner">
      <div class="label">AI Opportunity Readiness</div>
      <div class="value">{readiness_label}</div>
    </div>
  </div>

  <!-- 2. What We Heard -->
  <div class="section">
    <h2>2. What We Heard</h2>
    <p style="color:var(--ink-3);font-size:14px;margin-bottom:12px;">Please review this summary of your submission. If anything is incorrect, please contact us.</p>
    {what_we_heard}
  </div>

  <!-- 3. Top Opportunities -->
  <div class="section">
    <h2>3. Top Opportunities</h2>
    {opportunity_cards}
  </div>

  {onsite_note}

  <!-- 5. Recommended First Pilot -->
  <div class="section">
    <h2>5. Recommended First Pilot</h2>
    <div class="pilot-box">
      <h3>Objective</h3>
      <p>{_e(pilot.get('objective', ''))}</p>
      <h4>Scope</h4>
      <p>{_e(pilot.get('scope', ''))}</p>
      <h4>Exclusions</h4>
      <p>{_e(pilot.get('exclusions', ''))}</p>
      <h4>Suggested Duration</h4>
      <p>{_e(pilot.get('suggested_duration', ''))}</p>
      <h4>Success Metrics</h4>
      <ul>{''.join(f'<li>{_e(m)}</li>' for m in pilot.get('success_metrics', []))}</ul>
      <h4>What We Need From You</h4>
      <ul>{''.join(f'<li>{_e(n)}</li>' for n in pilot.get('needs_from_client', []))}</ul>
      <p style="margin-top:16px;color:var(--ink-3);font-size:14px;">A fixed-scope proposal can be prepared after a short validation call or on-site assessment.</p>
    </div>
  </div>

  <!-- 6. What Not to Automate Yet -->
  <div class="section">
    <h2>6. What Not to Automate Yet</h2>
    {not_recommended if not_recommended else '<p>Based on this assessment, no workflows have been flagged as unsuitable for future consideration.</p>'}
  </div>

  <!-- 7. Risks and Guardrails -->
  <div class="section">
    <h2>7. Risks and Guardrails</h2>
    <div class="risk-level-banner" style="background:{'#fef2f2' if scoring['risk_level']=='high' else '#fffbeb' if scoring['risk_level']=='medium' else '#f0fdf4'};padding:12px 16px;border-radius:8px;margin-bottom:16px;">
      <strong>Overall Risk Level: {scoring['risk_level'].upper()}</strong>
      {'— Medical/healthcare workflows require strict human oversight, data de-identification and professional compliance review.' if norm['is_medical'] else ''}
    </div>
    {risk_controls if risk_controls else '<p>No specific risks identified beyond standard implementation considerations.</p>'}
  </div>

  <!-- 8. Suggested 30/60/90-Day Path -->
  <div class="section">
    <h2>8. Suggested 30/60/90-Day Path</h2>
    <div class="path-grid">
      <div class="path-card">
        <h4>Days 0–30</h4>
        <p>{_e(path_30_60_90.get('days_0_30', ''))}</p>
      </div>
      <div class="path-card">
        <h4>Days 31–60</h4>
        <p>{_e(path_30_60_90.get('days_31_60', ''))}</p>
      </div>
      <div class="path-card">
        <h4>Days 61–90</h4>
        <p>{_e(path_30_60_90.get('days_61_90', ''))}</p>
      </div>
    </div>
  </div>

  <!-- 9. Next Step -->
  <div class="cta-section">
    <h3>{next_cta}</h3>
    <p>{next_desc}</p>
    <p style="font-size:13px;opacity:0.7;margin-top:16px;">Robin visits your workplace, listens to your team, and identifies where time is really being lost.</p>
  </div>

  <!-- Questions for On-site -->
  {"<div class='section'><h2>Questions for On-Site Discovery</h2><ol>" + questions + "</ol></div>" if questions else ""}

  <!-- Disclaimer -->
  <div class="disclaimer">
    <p><strong>Important Disclaimer</strong></p>
    <p>{_e(analysis.get('disclaimer', ''))}</p>
    <p style="margin-top:8px;">Snail AI · Suite 404, 53 Walker Street, North Sydney, NSW 2060 · robin@snailai.ai · 0417 993 551</p>
  </div>

</div>
</body>
</html>"""

    return html


def _e(text) -> str:
    """HTML 转义"""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))
