"""
Dashboard qualità aria — SDS011
Legge i 3 CSV prodotti dallo script di aggregazione e mostra 4 viste interattive.

Installazione dipendenze:
    pip install dash plotly pandas numpy

Avvio:
    python dashboard.py
    → apri http://127.0.0.1:8050 nel browser
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, callback
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────
output_dir   = Path("Output").resolve()
PATH_HOURLY  = output_dir / "hourly_aggregated.csv"
PATH_DAILY   = output_dir / "daily_aggregated.csv"
PATH_MONTHLY = output_dir / "monthly_aggregated.csv"

LIMITS_PM25 = {
    "WHO 2021 annuo":   {"value": 5,  "color": "#1D9E75", "dash": "dot"},
    "UE 2030 annuo":    {"value": 10, "color": "#378ADD", "dash": "dot"},
    "WHO 2021 24h":     {"value": 15, "color": "#EF9F27", "dash": "dash"},
    "UE attuale annuo": {"value": 25, "color": "#E24B4A", "dash": "dash"},
}

LIMITS_PM10 = {
    "WHO 2021 annuo":   {"value": 15, "color": "#1D9E75", "dash": "dot"},
    "UE 2030 annuo":    {"value": 20, "color": "#378ADD", "dash": "dot"},
    "WHO 2021 24h":     {"value": 45, "color": "#EF9F27", "dash": "dash"},
    "UE attuale annuo": {"value": 40, "color": "#E24B4A", "dash": "dash"},
    "UE attuale 24h":   {"value": 50, "color": "#993C1D", "dash": "longdash"},
}

# ─────────────────────────────────────────────
# CARICAMENTO DATI
# ─────────────────────────────────────────────
def load_data():
    hourly  = pd.read_csv(PATH_HOURLY,  index_col=0, parse_dates=True)
    daily   = pd.read_csv(PATH_DAILY,   index_col=0, parse_dates=True)
    monthly = pd.read_csv(PATH_MONTHLY, index_col=0, parse_dates=True)
    return hourly, daily, monthly

hourly, daily, monthly = load_data()

# ─────────────────────────────────────────────
# STILE
# ─────────────────────────────────────────────
COLORS = {
    "pm25":    "#E24B4A",
    "pm10":    "#378ADD",
    "bg":      "#f8f7f4",
    "card":    "#ffffff",
    "text":    "#2c2c2a",
    "muted":   "#888780",
    "good":    "#1D9E75",
    "humid":   "#378ADD",
    "low_cov": "#EF9F27",
    "bad":     "#E24B4A",
    "no_data": "#D3D1C7",
}

CARD_STYLE = {
    "backgroundColor": COLORS["card"],
    "borderRadius": "12px",
    "padding": "20px 24px",
    "marginBottom": "16px",
    "boxShadow": "0 1px 3px rgba(0,0,0,0.06)",
}

LABEL_STYLE = {
    "fontSize": "12px",
    "fontWeight": "500",
    "color": COLORS["muted"],
    "marginBottom": "12px",
    "letterSpacing": "0.04em",
    "textTransform": "uppercase",
}

QUALITY_LEGEND = [
    ("good",    "Good",            COLORS["good"],
     "Ora con ≥50% campioni ricevuti e ≥70% validi per umidità. Dati affidabili."),
    ("humid",   "Umido",           COLORS["humid"],
     "Campioni ricevuti ma scartati perché l'umidità superava il 70%: "
     "l'SDS011 confonde le goccioline d'acqua con particolato."),
    ("low_cov", "Bassa copertura", COLORS["low_cov"],
     "Pochi campioni ricevuti nell'ora (<50% dell'atteso): "
     "tipicamente WiFi instabile o riavvio del sensore."),
    ("bad",     "Bad",             COLORS["bad"],
     "Sia bassa copertura che umidità alta: ora da escludere da qualsiasi analisi."),
    ("no_data", "No data",         COLORS["no_data"],
     "Nessun campione ricevuto: sensore spento, disconnesso o caduta di rete prolungata."),
]

# ─────────────────────────────────────────────
# LAYOUT APP
# ─────────────────────────────────────────────
app = dash.Dash(__name__, title="Qualità aria — SDS011")

app.layout = html.Div(
    style={"backgroundColor": COLORS["bg"], "minHeight": "100vh",
           "fontFamily": "system-ui, sans-serif", "color": COLORS["text"]},
    children=[

        # ── Header ──────────────────────────────────────────────────────
        html.Div(
            style={"padding": "28px 32px 8px"},
            children=[
                html.H1("Qualità aria — SDS011",
                        style={"fontSize": "22px", "fontWeight": "500", "margin": 0}),
                html.P("Dati locali · sensor.community",
                       style={"fontSize": "13px", "color": COLORS["muted"], "margin": "4px 0 0"}),
            ]
        ),

        # ── Barra controlli ─────────────────────────────────────────────
        html.Div(
            style={**CARD_STYLE, "margin": "16px 32px", "display": "flex",
                   "gap": "32px", "alignItems": "flex-end", "flexWrap": "wrap"},
            children=[
                # Filtro date — sempre visibile
                html.Div([
                    html.Label("Intervallo date", style=LABEL_STYLE),
                    dcc.DatePickerRange(
                        id="date-range",
                        min_date_allowed=daily.index.min().date(),
                        max_date_allowed=daily.index.max().date(),
                        start_date=daily.index.min().date(),
                        end_date=daily.index.max().date(),
                        display_format="DD/MM/YYYY",
                        style={"fontSize": "13px"},
                    ),
                ]),
                # Solo giorni affidabili — sempre visibile
                html.Div([
                    html.Label("Solo giorni affidabili", style=LABEL_STYLE),
                    dcc.Checklist(
                        id="reliable-only",
                        options=[{"label": "  Filtra", "value": "yes"}],
                        value=["yes"],
                        inline=True,
                        style={"fontSize": "13px"},
                    ),
                ]),
                # Linee limite — nascosto/visibile via callback
                html.Div(
                    id="limits-control-wrapper",
                    children=[
                        html.Label("Mostra linee limite", style=LABEL_STYLE),
                        dcc.Checklist(
                            id="limits-toggle",
                            options=[{"label": f"  {k}", "value": k} for k in LIMITS_PM25],
                            value=["WHO 2021 24h", "UE attuale annuo"],
                            inline=True,
                            style={"fontSize": "13px", "gap": "16px"},
                        ),
                    ]
                ),
            ]
        ),

        # ── Tabs ────────────────────────────────────────────────────────
        html.Div(
            style={"padding": "0 32px 32px"},
            children=[
                dcc.Tabs(
                    id="tabs",
                    value="serie",
                    style={"marginBottom": "16px"},
                    colors={"border": "transparent", "primary": COLORS["text"],
                            "background": "transparent"},
                    children=[
                        dcc.Tab(label="Serie temporale",  value="serie"),
                        dcc.Tab(label="Heatmap oraria",   value="heatmap"),
                        dcc.Tab(label="Limiti normativi", value="limiti"),
                        dcc.Tab(label="Qualità dati",     value="qualita"),
                    ]
                ),
                html.Div(id="tab-content"),
            ]
        ),
    ]
)

# ─────────────────────────────────────────────
# CALLBACK: mostra/nascondi "linee limite"
# ─────────────────────────────────────────────
@callback(
    Output("limits-control-wrapper", "style"),
    Input("tabs", "value"),
)
def toggle_limits_control(tab):
    if tab in ("serie", "limiti"):
        return {"display": "block"}
    return {"display": "none"}


# ─────────────────────────────────────────────
# CALLBACK PRINCIPALE
# ─────────────────────────────────────────────
@callback(
    Output("tab-content", "children"),
    Input("tabs",          "value"),
    Input("date-range",    "start_date"),
    Input("date-range",    "end_date"),
    Input("limits-toggle", "value"),
    Input("reliable-only", "value"),
)
def render_tab(tab, start, end, selected_limits, reliable_flag):
    reliable_only = "yes" in (reliable_flag or [])
    d = filter_daily(start, end, reliable_only)

    if tab == "serie":
        return render_serie(d, start, end, selected_limits)
    if tab == "heatmap":
        return render_heatmap(start, end)
    if tab == "limiti":
        return render_limiti(d, selected_limits)
    if tab == "qualita":
        return render_qualita(d, start, end)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def filter_daily(start, end, reliable_only):
    mask = (daily.index >= pd.Timestamp(start)) & (daily.index <= pd.Timestamp(end))
    d = daily[mask].copy()
    if reliable_only:
        d = d[d["is_reliable"]]
    return d


def _add_limit_lines_paper(fig, limits_dict, selected_limits):
    """Linee limite su asse categorico (xref=paper, coordinate 0–1)."""
    for name, cfg in limits_dict.items():
        if name not in (selected_limits or []):
            continue
        fig.add_shape(
            type="line", xref="paper", yref="y",
            x0=0, x1=1,
            y0=cfg["value"], y1=cfg["value"],
            line={"color": cfg["color"], "width": 1.2, "dash": cfg["dash"]},
        )
        fig.add_annotation(
            xref="paper", yref="y",
            x=1, y=cfg["value"],
            text=f"{name} ({cfg['value']})",
            showarrow=False, xanchor="right",
            font={"size": 10, "color": cfg["color"]},
            bgcolor="rgba(255,255,255,0.7)",
        )


def _add_limit_lines_datetime(fig, limits_dict, selected_limits, x0, x1, row, col):
    """Linee limite su asse datetime (xref=x, coordinate reali)."""
    # xref/yref nei subplots: row 1 = "x"/"y", row 2 = "x2"/"y2"
    xref = "x" if row == 1 else f"x{row}"
    yref = "y" if row == 1 else f"y{row}"
    for name, cfg in limits_dict.items():
        if name not in (selected_limits or []):
            continue
        fig.add_shape(
            type="line", xref=xref, yref=yref,
            x0=x0, x1=x1,
            y0=cfg["value"], y1=cfg["value"],
            line={"color": cfg["color"], "width": 1.2, "dash": cfg["dash"]},
            row=row, col=col,
        )
        fig.add_annotation(
            xref=xref, yref=yref,
            x=x1, y=cfg["value"],
            text=f"{name} ({cfg['value']})",
            showarrow=False, xanchor="right",
            font={"size": 10, "color": cfg["color"]},
            bgcolor="rgba(255,255,255,0.7)",
            row=row, col=col,
        )


def _layout():
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "font":      {"family": "system-ui, sans-serif", "size": 12, "color": COLORS["text"]},
        "margin":    {"t": 40, "b": 20, "l": 50, "r": 20},
        "hovermode": "x unified",
        "xaxis":     {"showgrid": False, "zeroline": False},
        "yaxis":     {"gridcolor": "#e8e6e0", "zeroline": False},
    }


def _btn_style(active):
    return {
        "padding": "6px 18px",
        "borderRadius": "99px",
        "border": f"1px solid {'#2c2c2a' if active else '#D3D1C7'}",
        "backgroundColor": "#2c2c2a" if active else COLORS["card"],
        "color": "#ffffff" if active else COLORS["text"],
        "fontSize": "13px",
        "fontWeight": "500",
        "cursor": "pointer",
    }


def _build_exceedance_rows(d, col, limits_dict):
    rows = []
    for name, cfg in limits_dict.items():
        val = cfg["value"]
        if col not in d.columns:
            continue
        n_above = int((d[col] > val).sum())
        pct = n_above / len(d) * 100 if len(d) > 0 else 0
        rows.append(html.Tr([
            html.Td(name,           style={"padding": "8px 12px", "fontSize": "13px"}),
            html.Td(f"{val} μg/m³", style={"padding": "8px 12px", "fontSize": "13px"}),
            html.Td(f"{n_above} giorni",
                    style={"padding": "8px 12px", "fontSize": "13px",
                           "color": COLORS["pm25"] if n_above > 0 else COLORS["good"]}),
            html.Td(f"{pct:.1f}%",  style={"padding": "8px 12px", "fontSize": "13px"}),
        ]))
    return rows


def _build_table(rows, title):
    return [
        html.P(title, style=LABEL_STYLE),
        html.Table(
            style={"width": "100%", "borderCollapse": "collapse"},
            children=[
                html.Thead(html.Tr([
                    html.Th(h, style={
                        "padding": "8px 12px", "fontSize": "12px",
                        "color": COLORS["muted"], "textAlign": "left",
                        "borderBottom": f"1px solid {COLORS['no_data']}",
                    })
                    for h in ["Limite", "Valore", "Giorni superati", "% giorni"]
                ])),
                html.Tbody(rows),
            ]
        ),
    ]


# ─────────────────────────────────────────────
# TAB 1 — SERIE TEMPORALE
# ─────────────────────────────────────────────
def render_serie(d, start, end, selected_limits):
    if d.empty:
        return html.P("Nessun dato nel periodo selezionato.",
                      style={"color": COLORS["muted"], "padding": "32px"})

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=("PM2.5 (μg/m³)", "PM10 (μg/m³)"),
    )

    x0, x1 = d.index.min(), d.index.max()

    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm25_mean"], name="PM2.5 media",
        line={"color": COLORS["pm25"], "width": 1.5},
        hovertemplate="%{x|%d/%m/%Y}<br>PM2.5: %{y:.1f} μg/m³<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm25_max"], name="PM2.5 max",
        line={"color": COLORS["pm25"], "width": 0.5, "dash": "dot"},
        opacity=0.4,
        hovertemplate="%{x|%d/%m/%Y}<br>PM2.5 max: %{y:.1f} μg/m³<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm10_mean"], name="PM10 media",
        line={"color": COLORS["pm10"], "width": 1.5},
        hovertemplate="%{x|%d/%m/%Y}<br>PM10: %{y:.1f} μg/m³<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm10_max"], name="PM10 max",
        line={"color": COLORS["pm10"], "width": 0.5, "dash": "dot"},
        opacity=0.4,
        hovertemplate="%{x|%d/%m/%Y}<br>PM10 max: %{y:.1f} μg/m³<extra></extra>",
    ), row=2, col=1)

    _add_limit_lines_datetime(fig, LIMITS_PM25, selected_limits, x0, x1, row=1, col=1)
    _add_limit_lines_datetime(fig, LIMITS_PM10, selected_limits, x0, x1, row=2, col=1)

    fig.update_layout(**_layout())
    fig.update_yaxes(rangemode="tozero")

    return dcc.Graph(figure=fig, style={"height": "580px"})


# ─────────────────────────────────────────────
# TAB 2 — HEATMAP ORARIA
# ─────────────────────────────────────────────
def render_heatmap(start, end):
    return html.Div([
        html.Div(
            style={"display": "flex", "gap": "8px", "marginBottom": "16px"},
            children=[
                html.Button("PM2.5", id="heatmap-btn-pm25", n_clicks=0,
                            style=_btn_style(active=True)),
                html.Button("PM10",  id="heatmap-btn-pm10", n_clicks=0,
                            style=_btn_style(active=False)),
            ]
        ),
        html.Div(id="heatmap-graph-container"),
        html.P(
            "Solo ore con qualità 'good'. Valori medi per ora × giorno della settimana.",
            style={"fontSize": "12px", "color": COLORS["muted"], "marginTop": "8px"},
        ),
    ])


@callback(
    Output("heatmap-graph-container", "children"),
    Output("heatmap-btn-pm25",        "style"),
    Output("heatmap-btn-pm10",        "style"),
    Input("heatmap-btn-pm25",  "n_clicks"),
    Input("heatmap-btn-pm10",  "n_clicks"),
    Input("date-range",        "start_date"),
    Input("date-range",        "end_date"),
    Input("tabs",              "value"),
)
def update_heatmap(n25, n10, start, end, tab):
    if tab != "heatmap":
        return dash.no_update, dash.no_update, dash.no_update

    ctx = dash.callback_context
    triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else "heatmap-btn-pm25.n_clicks"
    use_pm25 = "pm10" not in triggered

    metric_col   = "pm25_mean" if use_pm25 else "pm10_mean"
    metric_label = "PM2.5"     if use_pm25 else "PM10"
    metric_color = COLORS["pm25"] if use_pm25 else COLORS["pm10"]

    mask = (
        (hourly.index >= pd.Timestamp(start)) &
        (hourly.index <= pd.Timestamp(end)) &
        (hourly["quality"] == "good")
    )
    h = hourly[mask].copy()

    if h.empty or metric_col not in h.columns:
        graph = html.P("Nessun dato nel periodo selezionato.",
                       style={"color": COLORS["muted"], "padding": "32px"})
    else:
        DAYS    = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        day_map = {0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì",
                   4: "Venerdì", 5: "Sabato", 6: "Domenica"}

        h["hour"]    = h.index.hour
        h["weekday"] = h.index.weekday.map(day_map)

        pivot = h.pivot_table(
            values=metric_col, index="hour", columns="weekday", aggfunc="mean"
        ).reindex(columns=DAYS)

        fig = go.Figure(go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=[f"{i:02d}:00" for i in pivot.index],
            colorscale=[
                [0.0, "#E1F5EE"],
                [0.2, "#9FE1CB"],
                [0.4, "#EF9F27"],
                [0.7, metric_color],
                [1.0, "#501313"],
            ],
            hovertemplate=f"%{{x}} %{{y}}<br>{metric_label}: %{{z:.1f}} μg/m³<extra></extra>",
            colorbar={"title": "μg/m³", "thickness": 14},
        ))

        fig.update_layout(**_layout())
        fig.update_yaxes(autorange="reversed", title="Ora del giorno")
        fig.update_xaxes(title="")

        graph = dcc.Graph(figure=fig, style={"height": "500px"})

    return graph, _btn_style(active=use_pm25), _btn_style(active=not use_pm25)


# ─────────────────────────────────────────────
# TAB 3 — LIMITI NORMATIVI
# ─────────────────────────────────────────────
def render_limiti(d, selected_limits):
    if d.empty:
        return html.P("Nessun dato nel periodo selezionato.",
                      style={"color": COLORS["muted"], "padding": "32px"})

    m = monthly[
        (monthly.index >= pd.Timestamp(d.index.min())) &
        (monthly.index <= pd.Timestamp(d.index.max()))
    ].copy()

    if m.empty:
        return html.P("Nessun dato mensile nel periodo selezionato.",
                      style={"color": COLORS["muted"], "padding": "32px"})

    x_labels = m.index.strftime("%b %Y").tolist()

    # Colori barre PM2.5
    bar_colors_25 = []
    for val in m["pm25_mean"]:
        if pd.isna(val):  bar_colors_25.append(COLORS["no_data"])
        elif val <= 5:    bar_colors_25.append("#1D9E75")
        elif val <= 10:   bar_colors_25.append("#5DCAA5")
        elif val <= 15:   bar_colors_25.append("#EF9F27")
        elif val <= 25:   bar_colors_25.append("#E24B4A")
        else:             bar_colors_25.append("#501313")

    # Colori barre PM10
    bar_colors_10 = []
    for val in m["pm10_mean"]:
        if pd.isna(val):  bar_colors_10.append(COLORS["no_data"])
        elif val <= 15:   bar_colors_10.append("#1D9E75")
        elif val <= 20:   bar_colors_10.append("#5DCAA5")
        elif val <= 40:   bar_colors_10.append("#EF9F27")
        elif val <= 50:   bar_colors_10.append("#E24B4A")
        else:             bar_colors_10.append("#501313")

    fig25 = go.Figure()
    fig25.add_trace(go.Bar(
        x=x_labels, y=m["pm25_mean"], marker_color=bar_colors_25,
        hovertemplate="%{x}<br>PM2.5 media: %{y:.1f} μg/m³<extra></extra>",
    ))
    _add_limit_lines_paper(fig25, LIMITS_PM25, selected_limits)
    fig25.update_layout(**_layout(), showlegend=False,
                        title={"text": "PM2.5 — media mensile (μg/m³)",
                               "font": {"size": 13}, "x": 0})
    fig25.update_yaxes(rangemode="tozero")
    fig25.update_xaxes(title="")

    fig10 = go.Figure()
    fig10.add_trace(go.Bar(
        x=x_labels, y=m["pm10_mean"], marker_color=bar_colors_10,
        hovertemplate="%{x}<br>PM10 media: %{y:.1f} μg/m³<extra></extra>",
    ))
    _add_limit_lines_paper(fig10, LIMITS_PM10, selected_limits)
    fig10.update_layout(**_layout(), showlegend=False,
                        title={"text": "PM10 — media mensile (μg/m³)",
                               "font": {"size": 13}, "x": 0})
    fig10.update_yaxes(rangemode="tozero")
    fig10.update_xaxes(title="")

    nota = html.P(
        "I grafici mostrano la media mensile di concentrazione (μg/m³), "
        "che è la misura usata da WHO e UE per i limiti normativi. "
        "La somma non è usata perché sommare concentrazioni di giorni diversi "
        "non ha significato fisico — è come sommare le temperature di gennaio.",
        style={"fontSize": "12px", "color": COLORS["muted"],
               "margin": "4px 0 16px", "fontStyle": "italic"},
    )

    rows_25 = _build_exceedance_rows(d, "pm25_mean", LIMITS_PM25)
    rows_10 = _build_exceedance_rows(d, "pm10_mean", LIMITS_PM10)

    return html.Div([
        nota,
        dcc.Graph(figure=fig25, style={"height": "300px"}),
        dcc.Graph(figure=fig10, style={"height": "300px", "marginTop": "8px"}),
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginTop": "16px"},
            children=[
                html.Div(style={**CARD_STYLE, "flex": "1", "minWidth": "300px"},
                         children=_build_table(rows_25, "PM2.5 — giorni di superamento")),
                html.Div(style={**CARD_STYLE, "flex": "1", "minWidth": "300px"},
                         children=_build_table(rows_10, "PM10 — giorni di superamento")),
            ]
        ),
    ])


# ─────────────────────────────────────────────
# TAB 4 — QUALITÀ DATI
# ─────────────────────────────────────────────
def render_qualita(d, start, end):
    mask = (
        (hourly.index >= pd.Timestamp(start)) &
        (hourly.index <= pd.Timestamp(end))
    )
    h = hourly[mask].copy()

    quality_daily = (
        h.groupby(h.index.date)["quality"]
        .value_counts()
        .unstack(fill_value=0)
    )
    for q, *_ in QUALITY_LEGEND:
        if q not in quality_daily.columns:
            quality_daily[q] = 0

    x_labels = [str(dt) for dt in quality_daily.index]

    fig = go.Figure()
    for q, label, color, _ in QUALITY_LEGEND:
        fig.add_trace(go.Bar(
            x=x_labels, y=quality_daily[q],
            name=label, marker_color=color,
            hovertemplate=f"{label}: %{{y}} ore<extra></extra>",
        ))

    fig.update_layout(**_layout(), barmode="stack",
                      legend={"orientation": "h", "y": -0.15})
    fig.update_yaxes(title="Ore", range=[0, 24])
    fig.update_xaxes(title="")

    # Legenda descrittiva
    legend_items = []
    for _, label, color, description in QUALITY_LEGEND:
        legend_items.append(
            html.Div(
                style={"display": "flex", "gap": "12px",
                       "alignItems": "flex-start", "marginBottom": "12px"},
                children=[
                    html.Div(style={
                        "width": "12px", "height": "12px", "borderRadius": "3px",
                        "backgroundColor": color, "flexShrink": "0", "marginTop": "3px",
                    }),
                    html.Div([
                        html.Span(label,
                                  style={"fontWeight": "500", "fontSize": "13px"}),
                        html.Span(f" — {description}",
                                  style={"fontSize": "13px", "color": COLORS["muted"]}),
                    ]),
                ]
            )
        )

    # KPI mensili
    m = monthly[
        (monthly.index >= pd.Timestamp(start)) &
        (monthly.index <= pd.Timestamp(end))
    ]
    kpi_cards = []
    for _, row in m.iterrows():
        cov   = row.get("coverage_pct", np.nan)
        color = COLORS["good"] if (not pd.isna(cov) and cov >= 75) else COLORS["bad"]
        kpi_cards.append(html.Div(
            style={**CARD_STYLE, "textAlign": "center", "minWidth": "100px", "flex": "1"},
            children=[
                html.P(row.name.strftime("%b %Y"),
                       style={"fontSize": "12px", "color": COLORS["muted"], "margin": "0 0 4px"}),
                html.P(f"{cov:.0f}%" if not pd.isna(cov) else "—",
                       style={"fontSize": "24px", "fontWeight": "500",
                              "color": color, "margin": 0}),
                html.P("giorni affidabili",
                       style={"fontSize": "11px", "color": COLORS["muted"], "margin": "2px 0 0"}),
            ]
        ))

    return html.Div([
        dcc.Graph(figure=fig, style={"height": "400px"}),
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "marginTop": "16px"},
            children=[
                html.Div(
                    style={**CARD_STYLE, "flex": "2", "minWidth": "320px"},
                    children=[
                        html.P("Cosa significa ogni categoria", style=LABEL_STYLE),
                        *legend_items,
                    ]
                ),
                html.Div(
                    style={"flex": "1", "minWidth": "200px"},
                    children=[
                        html.P("Copertura mensile",
                               style={**LABEL_STYLE, "marginBottom": "8px"}),
                        html.Div(
                            style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                            children=kpi_cards,
                        ),
                    ]
                ),
            ]
        ),
    ])


# ─────────────────────────────────────────────
# AVVIO
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)