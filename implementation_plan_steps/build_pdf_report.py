import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (Pages 2+)
        if self._pageNumber > 1:
            self.drawString(54, 750, "HabitPulse: AI Cross-Habit Intelligence Implementation Plan")
            self.drawRightString(612 - 54, 750, "Confidential - Architecture Blueprint")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(54, 742, 612 - 54, 742)

        # Footer (All pages)
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 612 - 54, 45)
        
        self.drawString(54, 32, "HabitPulse Platform | Multi-Tenant Django + pgvector + Gemini Flash ($0.00/mo)")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(612 - 54, 32, page_text)
        self.restoreState()

def build_pdf(output_pdf_path):
    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0F172A") # Deep Navy
    accent_color = colors.HexColor("#0284C7")  # Deep Sky Blue
    charcoal = colors.HexColor("#334155")
    bg_light = colors.HexColor("#F8FAFC")
    border_color = colors.HexColor("#CBD5E1")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=primary_color,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=accent_color,
        spaceAfter=15
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=primary_color,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=accent_color,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=charcoal,
        spaceAfter=6
    )

    code_style = ParagraphStyle(
        'Code_Custom',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1E293B")
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=charcoal,
        leftIndent=15,
        spaceAfter=3
    )

    story = []

    # Title & Header
    story.append(Paragraph("HabitPulse: AI-Powered Cross-Habit Intelligence", title_style))
    story.append(Paragraph("Master Technical Specification & Step-by-Step Implementation Blueprint", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=accent_color, spaceAfter=12))

    # Meta Info Card
    meta_data = [
        [Paragraph("<b>Document Version:</b> 1.0.0", body_style), Paragraph("<b>Target Architecture:</b> Django 4.2 LTS + PostgreSQL 16 (pgvector)", body_style)],
        [Paragraph("<b>Status:</b> Production Ready for Implementation", body_style), Paragraph("<b>Operational Cost:</b> $0.00 / month (100% Free Stack)", body_style)],
        [Paragraph("<b>Target Directory:</b> /habits", body_style), Paragraph("<b>AI Engine:</b> Gemini 1.5 Flash (Free Tier)", body_style)]
    ]
    meta_table = Table(meta_data, colWidths=[240, 264])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg_light),
        ('BOX', (0,0), (-1,-1), 1, border_color),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # Section 1
    story.append(Paragraph("1. Executive Summary & The Six-Stage Behavioral Loop", h1_style))
    story.append(Paragraph(
        "Current habit tracking applications operate as <b>isolated checkbox recorders</b>. They record whether a user completed 'Gym' or 'Meditation' as independent rows, ignoring that human habits form an interconnected biological and psychological ecosystem. A poor night of sleep directly reduces gym stamina; inadequate hydration creates afternoon fatigue that destroys evening reading habits.",
        body_style
    ))
    story.append(Paragraph(
        "HabitPulse implements the complete six-stage behavioral loop:",
        body_style
    ))
    
    loop_data = [
        [Paragraph("<b>Stage</b>", body_style), Paragraph("<b>Core Objective</b>", body_style), Paragraph("<b>Technical Mechanism</b>", body_style)],
        [Paragraph("1. Track", body_style), Paragraph("Capture micro-metrics and context", body_style), Paragraph("Duration, value, time, location, 1-tap energy slider", body_style)],
        [Paragraph("2. Understand", body_style), Paragraph("Recognize daily human context", body_style), Paragraph("Energy rating (1-5), stress (Low/Med/High), sleep hours", body_style)],
        [Paragraph("3. Connect", body_style), Paragraph("Identify relationships across habits", body_style), Paragraph("Lagged correlation matrix (Day t-1 impact on Day t)", body_style)],
        [Paragraph("4. Analyze", body_style), Paragraph("Eliminate spurious correlations", body_style), Paragraph("Domain-constrained hypothesis priors (biological rules)", body_style)],
        [Paragraph("5. Recommend", body_style), Paragraph("Prescribe one high-leverage lever", body_style), Paragraph("Grounded RAG synthesis via Google Gemini 1.5 Flash", body_style)],
        [Paragraph("6. Improve", body_style), Paragraph("Sustainable lifestyle progression", body_style), Paragraph("Habit stacking, progressive overload, micro-downgrades", body_style)]
    ]
    loop_table = Table(loop_data, colWidths=[80, 200, 224])
    loop_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('TEXTCOLOR', (0,0), (-1,0), primary_color),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, bg_light]),
    ]))
    story.append(loop_table)
    story.append(Spacer(1, 14))

    # Section 2
    story.append(Paragraph("2. The Two-Tier Architecture: Zero Hallucination Guarantee", h1_style))
    story.append(Paragraph(
        "A critical pitfall in AI applications is passing raw logs directly to an LLM and asking it to 'find relationships'. This leads to hallucinations, false causality, and unscientific claims. HabitPulse employs a strict two-tier architecture:",
        body_style
    ))
    
    tier_data = [
        [Paragraph("<b>Architecture Tier</b>", body_style), Paragraph("<b>Engine & Responsibility</b>", body_style), Paragraph("<b>Guarantees & Safeguards</b>", body_style)],
        [
            Paragraph("<b>Tier 1: Deterministic Math</b>", body_style),
            Paragraph("Python math & statistical engine running inside Django backend. Calculates Pearson/Spearman correlation coefficients (r), p-values, and co-occurrence percentages across 14-30 day rolling windows.", body_style),
            Paragraph("100% deterministic, 0% hallucination. Ignores sample sizes N < 7. Evaluates temporal precedence (cause must precede effect).", body_style)
        ],
        [
            Paragraph("<b>Tier 2: Generative RAG Interpreter</b>", body_style),
            Paragraph("Google Gemini 1.5 Flash Free Tier grounded with behavioral science knowledge chunks from PostgreSQL pgvector.", body_style),
            Paragraph("Strict JSON output schema. Takes mathematically proven facts from Tier 1 and translates them into empathetic, motivating coaching advice.", body_style)
        ]
    ]
    tier_table = Table(tier_data, colWidths=[120, 230, 154])
    tier_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, bg_light]),
    ]))
    story.append(tier_table)
    story.append(Spacer(1, 14))

    # Section 3
    story.append(Paragraph("3. New Data Models & Schema Specifications", h1_style))
    story.append(Paragraph(
        "All additions are strictly additive, non-destructive, and respect multi-tenant workspace isolation:",
        body_style
    ))

    models_data = [
        [Paragraph("<b>Model Name</b>", body_style), Paragraph("<b>File Location</b>", body_style), Paragraph("<b>Key Fields & Types</b>", body_style), Paragraph("<b>Purpose</b>", body_style)],
        [
            Paragraph("<b>DailyUserCheckin</b>", body_style),
            Paragraph("habits/models_intelligence.py", body_style),
            Paragraph("user (FK), tenant (FK), checkin_date (Date), energy_level (1-5), stress_level (LOW/MED/HIGH), sleep_hours (Decimal)", body_style),
            Paragraph("Captures daily context in 3 seconds without survey burnout.", body_style)
        ],
        [
            Paragraph("<b>HabitCrossCorrelation</b>", body_style),
            Paragraph("habits/models_intelligence.py", body_style),
            Paragraph("primary_habit (FK), secondary_habit (FK), relationship_type (SYNERGY/FRICTION/LAG_RECOVERY), coefficient (Decimal), confidence (Decimal)", body_style),
            Paragraph("Stores verified mathematical correlations between habit pairs.", body_style)
        ],
        [
            Paragraph("<b>KnowledgeChunk</b>", body_style),
            Paragraph("habits/models_intelligence.py", body_style),
            Paragraph("category (Char), title (Char), content (Text), embedding (VectorField 768-dim), source_attribution (Char)", body_style),
            Paragraph("Stores curated behavioral science literature for RAG retrieval.", body_style)
        ],
        [
            Paragraph("<b>AICoachInsight</b>", body_style),
            Paragraph("habits/models_intelligence.py", body_style),
            Paragraph("user (FK), tenant (FK), insight_type (WARNING/REINFORCE/RECOMMEND), title (Char), body (Text), actionable_step (Char), is_pinned (Bool)", body_style),
            Paragraph("Stores personalized coaching insights surfaced on user dashboard.", body_style)
        ]
    ]
    models_table = Table(models_data, colWidths=[100, 110, 184, 110])
    models_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, bg_light]),
    ]))
    story.append(models_table)
    story.append(Spacer(1, 14))

    # Page Break for Phase-by-phase implementation plan
    story.append(PageBreak())

    # Section 4
    story.append(Paragraph("4. Step-by-Step Implementation Roadmap (Handoff Instructions)", h1_style))
    story.append(Paragraph(
        "The executing agent/developer should implement this system in four consecutive, test-verified phases:",
        body_style
    ))

    # Phase 1
    story.append(Paragraph("Phase 1: Context Layer & Micro-Checkin UI (Immediate Start)", h2_style))
    story.append(Paragraph("<b>Step 1.1:</b> Create <code>habits/models_intelligence.py</code> with <code>DailyUserCheckin</code> and <code>AICoachInsight</code> models.", bullet_style))
    story.append(Paragraph("<b>Step 1.2:</b> Import intelligence models into <code>habits/models.py</code> and <code>habits/admin.py</code>.", bullet_style))
    story.append(Paragraph("<b>Step 1.3:</b> Generate additive migration: <code>python manage.py makemigrations habits</code> and run <code>python manage.py migrate</code>.", bullet_style))
    story.append(Paragraph("<b>Step 1.4:</b> Implement <code>record_daily_checkin(user, tenant, energy, stress, sleep, note)</code> in <code>habits/services_intelligence.py</code>.", bullet_style))
    story.append(Paragraph("<b>Step 1.5:</b> Add 1-tap energy slider & stress pills component to <code>templates/dashboard/dashboard.html</code> with AJAX submission.", bullet_style))
    story.append(Paragraph("<b>Step 1.6:</b> Write comprehensive tests in <code>tests/test_daily_checkin.py</code> (verifying daily uniqueness, tenant scoping, validation).", bullet_style))
    story.append(Spacer(1, 8))

    # Phase 2
    story.append(Paragraph("Phase 2: Mathematical Correlation Engine", h2_style))
    story.append(Paragraph("<b>Step 2.1:</b> Create <code>CrossHabitAnalyticsService</code> in <code>habits/services_correlation.py</code>.", bullet_style))
    story.append(Paragraph("<b>Step 2.2:</b> Implement <code>build_daily_behavior_matrix(user, tenant, lookback_days=30)</code> aggregating completion status, durations, and energy.", bullet_style))
    story.append(Paragraph("<b>Step 2.3:</b> Implement <code>compute_lagged_correlations()</code> evaluating Day t-1 Sleep/Water against Day t Gym/Focus habit duration.", bullet_style))
    story.append(Paragraph("<b>Step 2.4:</b> Implement Domain Prior Filter rejecting spurious non-biological correlations (e.g. ignoring flossing vs reading).", bullet_style))
    story.append(Paragraph("<b>Step 2.5:</b> Write unit tests in <code>tests/test_cross_habit_correlations.py</code> with synthetic multi-day behavioral datasets.", bullet_style))
    story.append(Spacer(1, 8))

    # Phase 3
    story.append(Paragraph("Phase 3: Zero-Cost RAG Vector Engine ($0.00 Cost)", h2_style))
    story.append(Paragraph("<b>Step 3.1:</b> Update <code>docker-compose.yml</code> database image to <code>pgvector/pgvector:pg16</code> and restart containers.", bullet_style))
    story.append(Paragraph("<b>Step 3.2:</b> Enable vector extension in PostgreSQL: <code>CREATE EXTENSION IF NOT EXISTS vector;</code>.", bullet_style))
    story.append(Paragraph("<b>Step 3.3:</b> Create <code>KnowledgeChunk</code> model with 768-dimensional VectorField.", bullet_style))
    story.append(Paragraph("<b>Step 3.4:</b> Build seed management command <code>habits/management/commands/seed_rag_knowledge.py</code> with 50+ curated science chunks.", bullet_style))
    story.append(Paragraph("<b>Step 3.5:</b> Implement <code>retrieve_relevant_coaching_context(query_text, top_k=3)</code> using cosine similarity search in Django ORM.", bullet_style))
    story.append(Spacer(1, 8))

    # Phase 4
    story.append(Paragraph("Phase 4: AI Personal Growth Coach & Weekly Digest", h2_style))
    story.append(Paragraph("<b>Step 4.1:</b> Implement <code>generate_weekly_coach_digest(user, tenant)</code> in <code>habits/services_coach.py</code> using Gemini 1.5 Flash.", bullet_style))
    story.append(Paragraph("<b>Step 4.2:</b> Create dashboard Coach Drawer UI (<code>templates/dashboard/includes/ai_coach_drawer.html</code>) with chat Q&A.", bullet_style))
    story.append(Paragraph("<b>Step 4.3:</b> Add API endpoints <code>/api/coach/chat/</code> and <code>/api/coach/insights/vote/</code> for interactive feedback.", bullet_style))
    story.append(Paragraph("<b>Step 4.4:</b> Write automated view tests in <code>tests/test_ai_coach_views.py</code> with mocked LLM calls for lightning-fast CI/CD.", bullet_style))
    story.append(Spacer(1, 14))

    # Section 5: Anti-Hallucination Priors
    story.append(Paragraph("5. Domain Prior Filter & Anti-Hallucination Guardrails", h1_style))
    story.append(Paragraph(
        "To ensure the AI never embarrasses the product with silly correlations, statistical findings are filtered against a verified scientific prior dictionary:",
        body_style
    ))

    priors_data = [
        [Paragraph("<b>Prior Category</b>", body_style), Paragraph("<b>Permitted Hypothesis Pathway</b>", body_style), Paragraph("<b>Behavioral Science Grounding</b>", body_style)],
        [
            Paragraph("Sleep -> Fitness", body_style),
            Paragraph("Sleep duration/latency -> Workout completion & duration", body_style),
            Paragraph("Sleep deficit reduces muscle glycogen synthesis and raises perceived exertion.", body_style)
        ],
        [
            Paragraph("Hydration -> Stamina", body_style),
            Paragraph("Daily water logged -> Aerobic duration & evening energy", body_style),
            Paragraph("Even 2% dehydration impairs aerobic endurance by 15% and causes headache fatigue.", body_style)
        ],
        [
            Paragraph("Stress -> Habit Volume", body_style),
            Paragraph("High work stress day -> Failure of complex habits", body_style),
            Paragraph("BJ Fogg Model: When cognitive load spikes, ability collapses; micro-downgrades required.", body_style)
        ],
        [
            Paragraph("Habit Stacking", body_style),
            Paragraph("Anchor habit (streak > 21) -> New habit execution", body_style),
            Paragraph("Existing automatic neural pathways act as reliable cues for nascent routines.", body_style)
        ]
    ]
    priors_table = Table(priors_data, colWidths=[110, 194, 200])
    priors_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, bg_light]),
    ]))
    story.append(priors_table)
    story.append(Spacer(1, 14))

    # Section 6: Zero Cost Guarantees
    story.append(Paragraph("6. Zero-Cost Operational Budget Audit ($0.00 / Month)", h1_style))
    story.append(Paragraph(
        "Every single component has been engineered to operate completely free of charge, supporting up to 500 active users before any cloud tier upgrades are needed:",
        body_style
    ))

    cost_data = [
        [Paragraph("<b>Service / Component</b>", body_style), Paragraph("<b>Technology Used</b>", body_style), Paragraph("<b>Free Tier Allowance</b>", body_style), Paragraph("<b>Monthly Cost</b>", body_style)],
        [Paragraph("Vector Database", body_style), Paragraph("pgvector on PostgreSQL 16 (Docker)", body_style), Paragraph("Unlimited local/container storage", body_style), Paragraph("<b>$0.00</b>", body_style)],
        [Paragraph("LLM Reasoning & Chat", body_style), Paragraph("Google Gemini 1.5 Flash", body_style), Paragraph("1,500 requests/day, 15 RPM, 1M context", body_style), Paragraph("<b>$0.00</b>", body_style)],
        [Paragraph("Text Embeddings", body_style), Paragraph("Gemini text-embedding-004", body_style), Paragraph("1,500 requests/minute", body_style), Paragraph("<b>$0.00</b>", body_style)],
        [Paragraph("Correlation Math", body_style), Paragraph("Pure Python & PostgreSQL SQL", body_style), Paragraph("Local CPU / zero external APIs", body_style), Paragraph("<b>$0.00</b>", body_style)],
        [Paragraph("<b>Total Monthly Cost</b>", body_style), Paragraph("<b>Entire AI Stack</b>", body_style), Paragraph("<b>500 Daily Active Users</b>", body_style), Paragraph("<b>$0.00 / month</b>", body_style)]
    ]
    cost_table = Table(cost_data, colWidths=[110, 160, 164, 70])
    cost_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, bg_light]),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#DCFCE7")), # Light Green Highlight
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.HexColor("#166534")),
    ]))
    story.append(cost_table)
    story.append(Spacer(1, 14))

    # Section 7: Quality & Acceptance Checklist
    story.append(Paragraph("7. Quality Checklist & Definition of Done", h1_style))
    story.append(Paragraph(
        "The executing agent/developer must ensure all items pass before closing any implementation task:",
        body_style
    ))
    story.append(Paragraph("[ ] Zero database data loss: existing users, tenants, and habits remain 100% intact.", bullet_style))
    story.append(Paragraph("[ ] Multi-tenant isolation verified: checkins and insights are strictly scoped to request.tenant.", bullet_style))
    story.append(Paragraph("[ ] Statistical correlations tested with synthetic datasets covering positive, negative, and null scenarios.", bullet_style))
    story.append(Paragraph("[ ] External Gemini API calls wrapped in robust try/except with deterministic fallback templates.", bullet_style))
    story.append(Paragraph("[ ] All automated unit and view tests pass cleanly with pytest (exit code 0).", bullet_style))
    story.append(Paragraph("[ ] UI renders cleanly on mobile viewports (360px) and desktop (1440px).", bullet_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] PDF generated successfully at: {output_pdf_path}")

if __name__ == "__main__":
    output_path = os.path.join(os.path.dirname(__file__), "HabitPulse_AI_CrossHabit_Intelligence_Implementation_Plan.pdf")
    build_pdf(output_path)
