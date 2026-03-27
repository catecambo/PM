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
import plotly.express as px
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, callback
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURAZIONE — modifica questi path
# ─────────────────────────────────────────────
output_dir = Path("Output").resolve()
PATH_HOURLY = output_dir / "hourly_aggregated.csv"
PATH_DAILY = output_dir / "daily_aggregated.csv"
PATH_MONTHLY = output_dir / "monthly_aggregated.csv"

# Limiti normativi PM2.5 (μg/m³)
LIMITS = {
    "WHO 2021 annuo":   {"value": 5,  "color": "#1D9E75", "dash": "dot"},
    "UE 2030 annuo":    {"value": 10, "color": "#378ADD", "dash": "dot"},
    "WHO 2021 24h":     {"value": 15, "color": "#EF9F27", "dash": "dash"},
    "UE attuale annuo": {"value": 25, "color": "#E24B4A", "dash": "dash"},
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
    "pm25":       "#E24B4A",
    "pm10":       "#378ADD",
    "bg":         "#f8f7f4",
    "card":       "#ffffff",
    "text":       "#2c2c2a",
    "muted":      "#888780",
    "good":       "#1D9E75",
    "humid":      "#378ADD",
    "low_cov":    "#EF9F27",
    "bad":        "#E24B4A",
    "no_data":    "#D3D1C7",
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


# ─────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────
app = dash.Dash(__name__, title="Qualità aria — SDS011")

app.layout = html.Div(
    style={"backgroundColor": COLORS["bg"], "minHeight": "100vh",
           "fontFamily": "system-ui, sans-serif", "color": COLORS["text"]},
    children=[

        # Header
        html.Div(
            style={"padding": "28px 32px 8px"},
            children=[
                html.H1("Qualità aria — SDS011",
                        style={"fontSize": "22px", "fontWeight": "500", "margin": 0}),
                html.P("Dati locali · sensor.community",
                       style={"fontSize": "13px", "color": COLORS["muted"], "margin": "4px 0 0"}),
            ]
        ),

        # Controlli
        html.Div(
            style={**CARD_STYLE, "margin": "16px 32px", "display": "flex",
                   "gap": "32px", "alignItems": "flex-end", "flexWrap": "wrap"},
            children=[
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
                html.Div([
                    html.Label("Mostra linee limite", style=LABEL_STYLE),
                    dcc.Checklist(
                        id="limits-toggle",
                        options=[{"label": f"  {k}", "value": k} for k in LIMITS],
                        value=["WHO 2021 24h", "UE attuale annuo"],
                        inline=True,
                        style={"fontSize": "13px", "gap": "16px"},
                    ),
                ]),
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
            ]
        ),

        # Corpo principale
        html.Div(
            style={"padding": "0 32px 32px"},
            children=[

                # ── Tab navigation ─────────────────────────────────────
                dcc.Tabs(
                    id="tabs",
                    value="serie",
                    style={"marginBottom": "16px"},
                    colors={"border": "transparent", "primary": COLORS["text"],
                            "background": "transparent"},
                    children=[
                        dcc.Tab(label="Serie temporale",    value="serie"),
                        dcc.Tab(label="Heatmap oraria",     value="heatmap"),
                        dcc.Tab(label="Limiti normativi",   value="limiti"),
                        dcc.Tab(label="Qualità dati",       value="qualita"),
                    ]
                ),

                html.Div(id="tab-content"),
            ]
        ),
    ]
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def filter_daily(start, end, reliable_only):
    mask = (daily.index >= pd.Timestamp(start)) & (daily.index <= pd.Timestamp(end))
    d = daily[mask].copy()
    if reliable_only:
        d = d[d["is_reliable"]]
    return d


def add_limit_lines(fig, selected_limits, x_start, x_end, row=1, col=1):
    for name, cfg in LIMITS.items():
        if name not in selected_limits:
            continue
        fig.add_shape(
            type="line", xref="x", yref="y",
            x0=x_start, x1=x_end, y0=cfg["value"], y1=cfg["value"],
            line={"color": cfg["color"], "width": 1.2, "dash": cfg["dash"]},
            row=row, col=col,
        )
        fig.add_annotation(
            x=x_end, y=cfg["value"],
            text=f"{name} ({cfg['value']})",
            showarrow=False, xanchor="right",
            font={"size": 10, "color": cfg["color"]},
            bgcolor="rgba(255,255,255,0.7)",
            row=row, col=col,
        )


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
# TAB 1 — SERIE TEMPORALE
# ─────────────────────────────────────────────
def render_serie(d, start, end, selected_limits):
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("PM2.5 (μg/m³)", "PM10 (μg/m³)"),
    )

    # PM2.5
    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm25_mean"],
        name="PM2.5 media",
        line={"color": COLORS["pm25"], "width": 1.5},
        hovertemplate="%{x|%d/%m/%Y}<br>PM2.5: %{y:.1f} μg/m³<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm25_max"],
        name="PM2.5 max",
        line={"color": COLORS["pm25"], "width": 0.5, "dash": "dot"},
        opacity=0.5,
        hovertemplate="%{x|%d/%m/%Y}<br>PM2.5 max: %{y:.1f} μg/m³<extra></extra>",
    ), row=1, col=1)

    # PM10
    fig.add_trace(go.Scatter(
        x=d.index, y=d["pm10_mean"],
        name="PM10 media",
        line={"color": COLORS["pm10"], "width": 1.5},
        hovertemplate="%{x|%d/%m/%Y}<br>PM10: %{y:.1f} μg/m³<extra></extra>",
    ), row=2, col=1)

    # Linee limite solo su PM2.5
    x0, x1 = d.index.min(), d.index.max()
    add_limit_lines(fig, selected_limits, x0, x1, row=1, col=1)

    fig.update_layout(**_layout())
    fig.update_yaxes(rangemode="tozero")

    return dcc.Graph(figure=fig, style={"height": "520px"})


# ─────────────────────────────────────────────
# TAB 2 — HEATMAP ORARIA
# ─────────────────────────────────────────────
def render_heatmap(start, end):
    mask = (
        (hourly.index >= pd.Timestamp(start)) &
        (hourly.index <= pd.Timestamp(end)) &
        (hourly["quality"] == "good")
    )
    h = hourly[mask].copy()

    if h.empty:
        return html.P("Nessun dato nel periodo selezionato.",
                      style={"color": COLORS["muted"], "padding": "32px"})

    # Pivot: righe = ora del giorno, colonne = giorno settimana
    DAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    day_map = {0:"Lunedì",1:"Martedì",2:"Mercoledì",3:"Giovedì",
               4:"Venerdì",5:"Sabato",6:"Domenica"}

    h["hour"]    = h.index.hour
    h["weekday"] = h.index.weekday.map(day_map)

    pivot = h.pivot_table(
        values="pm25_mean", index="hour", columns="weekday", aggfunc="mean"
    ).reindex(columns=DAYS)

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=[f"{i:02d}:00" for i in pivot.index],
        colorscale=[
            [0.0,  "#E1F5EE"],
            [0.2,  "#9FE1CB"],
            [0.4,  "#EF9F27"],
            [0.7,  "#E24B4A"],
            [1.0,  "#501313"],
        ],
        hovertemplate="%{x} %{y}<br>PM2.5: %{z:.1f} μg/m³<extra></extra>",
        colorbar={"title": "μg/m³", "thickness": 14},
    ))

    fig.update_layout(**_layout())
    fig.update_yaxes(autorange="reversed", title="Ora del giorno")
    fig.update_xaxes(title="")

    note = html.P(
        "Solo ore con qualità 'good'. Valori medi per ora × giorno della settimana.",
        style={"fontSize": "12px", "color": COLORS["muted"], "marginTop": "8px"},
    )
    return html.Div([dcc.Graph(figure=fig, style={"height": "520px"}), note])


# ─────────────────────────────────────────────
# TAB 3 — CONFRONTO LIMITI NORMATIVI
# ─────────────────────────────────────────────
def render_limiti(d, selected_limits):
    if d.empty:
        return html.P("Nessun dato nel periodo selezionato.",
                      style={"color": COLORS["muted"], "padding": "32px"})

    # Grafico a barre mensili con linee limite
    m = monthly[
        (monthly.index >= pd.Timestamp(d.index.min())) &
        (monthly.index <= pd.Timestamp(d.index.max()))
    ].copy()

    bar_colors = []
    for val in m["pm25_mean"]:
        if pd.isna(val):      bar_colors.append(COLORS["no_data"])
        elif val <= 5:        bar_colors.append("#1D9E75")
        elif val <= 10:       bar_colors.append("#5DCAA5")
        elif val <= 15:       bar_colors.append("#EF9F27")
        elif val <= 25:       bar_colors.append("#E24B4A")
        else:                 bar_colors.append("#501313")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=m.index.strftime("%b %Y"),
        y=m["pm25_mean"],
        marker_color=bar_colors,
        name="PM2.5 media mensile",
        hovertemplate="%{x}<br>PM2.5: %{y:.1f} μg/m³<extra></extra>",
    ))

    x0 = m.index.strftime("%b %Y").iloc[0]
    x1 = m.index.strftime("%b %Y").iloc[-1]
    add_limit_lines(fig, selected_limits, x0, x1)

    fig.update_layout(
        **_layout(),
        yaxis={"title": "PM2.5 μg/m³", "rangemode": "tozero"},
        xaxis={"title": ""},
        showlegend=False,
    )

    # Tabella riepilogativa
    rows = []
    for name, cfg in LIMITS.items():
        if name not in selected_limits:
            continue
        fig.add_shape(
            type="line",
            xref="paper", yref="y",
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

    fig.update_layout(**_layout(), showlegend=False)
    fig.update_yaxes(title="PM2.5 μg/m³", rangemode="tozero")
    fig.update_xaxes(title="")

    # Tabella riepilogativa
    rows = []
    for name, cfg in LIMITS.items():
        val = cfg["value"]
        n_days_above = int((d["pm25_mean"] > val).sum())
        pct = n_days_above / len(d) * 100 if len(d) > 0 else 0
        rows.append(html.Tr([
            html.Td(name, style={"padding": "8px 12px", "fontSize": "13px"}),
            html.Td(f"{val} μg/m³", style={"padding": "8px 12px", "fontSize": "13px"}),
            html.Td(
                f"{n_days_above} giorni",
                style={"padding": "8px 12px", "fontSize": "13px",
                       "color": COLORS["pm25"] if n_days_above > 0 else COLORS["good"]},
            ),
            html.Td(f"{pct:.1f}%", style={"padding": "8px 12px", "fontSize": "13px"}),
        ]))

    table = html.Table(
        style={"width": "100%", "borderCollapse": "collapse", "marginTop": "16px"},
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
    )

    return html.Div([
        dcc.Graph(figure=fig, style={"height": "380px"}),
        html.Div(style=CARD_STYLE, children=[
            html.P("Giorni superamento nel periodo selezionato", style=LABEL_STYLE),
            table,
        ]),
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
    for col in ["good", "humid", "low_cov", "bad", "no_data"]:
        if col not in quality_daily.columns:
            quality_daily[col] = 0

    # FIX: converti l'indice date in stringhe con list comprehension
    # evita il comportamento inconsistente di .astype(str) su indici di tipo date
    x_labels = [str(d) for d in quality_daily.index]

    fig = go.Figure()
    for q, label, color in [
        ("good", "Good", COLORS["good"]),
        ("humid", "Umido", COLORS["humid"]),
        ("low_cov", "Bassa copertura", COLORS["low_cov"]),
        ("bad", "Bad", COLORS["bad"]),
        ("no_data", "No data", COLORS["no_data"]),
    ]:
        fig.add_trace(go.Bar(
            x=x_labels,
            y=quality_daily[q],
            name=label,
            marker_color=color,
            hovertemplate=f"{label}: %{{y}} ore<extra></extra>",
        ))

    # FIX: stessa soluzione heatmap — update_layout senza yaxis/xaxis,
    # poi update_yaxes/update_xaxes separati
    fig.update_layout(**_layout(), barmode="stack",
                      legend={"orientation": "h", "y": -0.15})
    fig.update_yaxes(title="Ore", range=[0, 24])
    fig.update_xaxes(title="")

    # KPI coverage mensile
    m = monthly[
        (monthly.index >= pd.Timestamp(start)) &
        (monthly.index <= pd.Timestamp(end))
        ]
    kpi_cards = []
    for _, row in m.iterrows():
        cov = row.get("coverage_pct", np.nan)
        color = COLORS["good"] if (not pd.isna(cov) and cov >= 75) else COLORS["bad"]
        kpi_cards.append(html.Div(
            style={**CARD_STYLE, "textAlign": "center", "minWidth": "120px", "flex": "1"},
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
        dcc.Graph(figure=fig, style={"height": "380px"}),
        html.Div(
            style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "16px"},
            children=kpi_cards,
        ),
    ])


# ─────────────────────────────────────────────
# LAYOUT COMUNE PLOTLY
# ─────────────────────────────────────────────
def _layout():
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "font":          {"family": "system-ui, sans-serif", "size": 12, "color": COLORS["text"]},
        "margin":        {"t": 40, "b": 20, "l": 50, "r": 20},
        "hovermode":     "x unified",
        "xaxis":         {"showgrid": False, "zeroline": False},
        "yaxis":         {"gridcolor": "#e8e6e0", "zeroline": False},
    }


# ─────────────────────────────────────────────
# AVVIO
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)