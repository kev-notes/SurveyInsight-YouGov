import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import colorsys

st.set_page_config(layout="wide", page_title="YouGov: Survey Dashboard")
st.title("YouGov — Survey Dashboard")
st.markdown(
    "Interactive dashboard: explore trends, survey distributions, and percent ranges across any response categories."
)

@st.cache_data
def load_and_clean(uploaded_file=None, default_path="publishing-salaries.xlsx"):
    path = uploaded_file if uploaded_file is not None else default_path

    xls = pd.ExcelFile(path)
    sheets = xls.sheet_names
    rows = []

    def parse_excel_date(s):
        if pd.isna(s):
            return pd.NaT
        s = str(s).strip()
        fmts = ["%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%b %Y", "%B %Y"]
        for fmt in fmts:
            try:
                return pd.to_datetime(s, format=fmt)
            except:
                continue
        try:
            return pd.to_datetime(s, dayfirst=True, errors="coerce")
        except:
            return pd.NaT

    for sheet in sheets:
        df = pd.read_excel(path, sheet_name=sheet)
        idcol = df.columns[0]
        # Remove rows with "Unweighted base" or "Base"
        df = df[~df[idcol].str.contains('Unweighted base|Base', case=False, na=False)]
        long = df.melt(id_vars=[idcol], var_name="date", value_name="value")
        long = long.rename(columns={idcol: "response"})
        long["date_parsed"] = long["date"].apply(parse_excel_date)
        long["date_parsed"] = long["date_parsed"].dt.normalize()

        def parse_value(x):
            if pd.isna(x):
                return np.nan
            s = str(x).strip().replace("%", "")
            try:
                return float(s)
            except:
                return np.nan

        long["value_num"] = long["value"].apply(parse_value)
        # shorten group name if long
        long["group"] = sheet if len(sheet) <= 50 else sheet[:50] + "..."
        rows.append(long)

    combined = pd.concat(rows, ignore_index=True)

    if combined["value_num"].dropna().max() > 1:
        combined["p"] = combined["value_num"] / 100.0
    else:
        combined["p"] = combined["value_num"]
    combined["p_percent"] = combined["p"] * 100

    # dynamically detect unique responses
    response_options = combined["response"].dropna().unique().tolist()

    return {"tidy": combined, "sheets": sheets, "responses": response_options}

# ---------------- Sidebar Global Filters ----------------
uploaded = st.sidebar.file_uploader("Upload Excel (optional)", type=["xlsx", "xls"])
data = load_and_clean(uploaded_file=uploaded)
sheets = data["sheets"]
response_options = data["responses"]

all_dates = data["tidy"]["date_parsed"].dropna().sort_values()
if all_dates.empty:
    st.error("No valid dates found in the dataset.")
    st.stop()

selected_groups = st.sidebar.multiselect("Select groups", options=sheets, default=[sheets[0]])
selected_responses = st.sidebar.multiselect(
    "Select responses", response_options, default=response_options
)
selected_date_range = st.sidebar.date_input(
    "Date range",
    value=(all_dates.min(), all_dates.max()),
    min_value=all_dates.min(),
    max_value=all_dates.max(),
)

filtered = data["tidy"][
    (data["tidy"]["group"].isin(selected_groups)) &
    (data["tidy"]["response"].isin(selected_responses)) &
    (data["tidy"]["date_parsed"] >= pd.to_datetime(selected_date_range[0])) &
    (data["tidy"]["date_parsed"] <= pd.to_datetime(selected_date_range[1]))
]

# ---------------- Chart Style ----------------
plotly_theme = dict(
    font=dict(family="Georgia, Times New Roman, serif", size=15, color="#222"),
    plot_bgcolor="white",
    paper_bgcolor="white",
    xaxis=dict(showgrid=True, gridcolor="#D9D9D9", zeroline=False, linecolor="#444", ticks="outside"),
    yaxis=dict(showgrid=True, gridcolor="#D9D9D9", zeroline=False, linecolor="#444", ticks="outside"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=13)),
    margin=dict(l=60, r=30, t=50, b=50),
)

def generate_colors(n):
    colors = []
    for i in range(n):
        hue = i / n
        lightness = 0.55
        saturation = 0.5
        rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
        colors.append(f'rgb({int(rgb[0]*255)},{int(rgb[1]*255)},{int(rgb[2]*255)})')
    return colors

palette = generate_colors(len(response_options))
response_colors = {resp: palette[i] for i, resp in enumerate(response_options)}
for i, resp in enumerate(response_options):
    response_colors[resp] = palette[i % len(palette)]

# # ---------------- Trend lines ----------------
# st.subheader("Trend lines — Percent over time")
# if filtered.empty:
#     st.info("No data for selected filters.")
# else:
#     fig = go.Figure()
#     for grp in selected_groups:
#         grpdf = filtered[filtered["group"] == grp]
#         for resp in selected_responses:
#             series = grpdf[grpdf["response"] == resp].sort_values("date_parsed")
#             if series.empty:
#                 continue
#             fig.add_trace(go.Scatter(
#                 x=series["date_parsed"], y=series["p_percent"], mode="lines+markers",
#                 name=f"{grp} — {resp}",
#                 line=dict(color=response_colors.get(resp, "#444"), width=2.5),
#                 marker=dict(size=5, symbol="circle"),
#                 hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}%<extra></extra>"
#             ))
#     fig.update_layout(**plotly_theme, yaxis_title="Percent (%)", height=480, hovermode="x unified")
#     st.plotly_chart(fig, use_container_width=True)

# ---------------- Survey distribution (Animated) ----------------
st.markdown("---")
st.subheader("Survey distribution — Animated across dates")
if filtered.empty:
    st.info("No data for survey distribution.")
else:
    pivoted = filtered.pivot_table(
        index=["date_parsed", "group"], columns="response", values="p_percent"
    ).fillna(0).reset_index()

    fig3 = go.Figure()
    init_date = pivoted["date_parsed"].min()
    init_df = pivoted[pivoted["date_parsed"] == init_date]
    for resp in selected_responses:
        fig3.add_trace(go.Bar(
            y=init_df["group"], x=init_df[resp], name=resp,
            marker=dict(color=response_colors.get(resp, "#444")),
            orientation="h", text=init_df[resp].round(1).astype(str)+"%",
            textposition="inside", insidetextanchor="middle"
        ))

    frames = []
    for d in pivoted["date_parsed"].unique():
        frame_df = pivoted[pivoted["date_parsed"] == d]
        data_bars = []
        for resp in selected_responses:
            data_bars.append(go.Bar(
                y=frame_df["group"], x=frame_df[resp], name=resp,
                marker=dict(color=response_colors.get(resp, "#444")),
                orientation="h", text=frame_df[resp].round(1).astype(str)+"%",
                textposition="inside", insidetextanchor="middle"
            ))
        frames.append(go.Frame(data=data_bars, name=str(d.date())))

    fig3.frames = frames
    fig3.update_layout(
        **plotly_theme,
        barmode="stack", xaxis_title="Percent (%)", height=480,
        updatemenus=[{
            "type": "buttons",
            "buttons": [
                {"label": "Play", "method": "animate", "args": [None, {"frame": {"duration": 1200, "redraw": True}, "fromcurrent": True}]},
                {"label": "Pause", "method": "animate", "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]}
            ]
        }],
        sliders=[{
            "steps": [
                {"label": str(d.date()), "method": "animate", "args": [[str(d.date())], {"mode": "immediate", "frame": {"duration": 600, "redraw": True}}]} 
                for d in pivoted["date_parsed"].unique()
            ],
            "active":0
        }]
    )
    st.plotly_chart(fig3, use_container_width=True)

# ---------------- Scatter range ----------------
st.markdown("---")
st.subheader("Scatter range — Percent range over selected dates")
if filtered.empty:
    st.info("No scatter range data for selected filters.")
else:
    fig_range = go.Figure()
    for grp in selected_groups:
        grpdf = filtered[filtered["group"]==grp]
        for resp in selected_responses:
            series = grpdf[grpdf["response"]==resp]
            if series.empty: continue
            min_val, max_val = series["p_percent"].min(), series["p_percent"].max()
            mean_val = series["p_percent"].mean()
            fig_range.add_trace(go.Scatter(
                x=[min_val,max_val], y=[grp,grp], mode="lines+markers",
                line=dict(width=5,color=response_colors.get(resp,"#444")),
                marker=dict(size=9,color=response_colors.get(resp,"#444")),
                name=resp,
                hovertemplate=f"{grp} — {resp}<br>Min: {min_val:.1f}%<br>Max: {max_val:.1f}%<br>Mean: {mean_val:.1f}%<extra></extra>",
                showlegend=(grp==selected_groups[0])
            ))
    fig_range.update_layout(**plotly_theme, xaxis_title="Percent (%)", yaxis_title="Group", height=480, hovermode="closest")
    st.plotly_chart(fig_range, use_container_width=True)

# ---------------- Data preview ----------------
st.markdown("---")
st.subheader("Filtered data preview")
if filtered.empty:
    st.write("No rows to show")
else:
    display_df = filtered.loc[:, ["group","date_parsed","response","p_percent"]].sort_values(["group","date_parsed","response"])
    display_df = display_df.rename(columns={"date_parsed":"date","p_percent":"percent"})
    st.dataframe(display_df)

# ---------------- Download ----------------
st.markdown("---")
st.subheader("Download filtered data")
csv_buf = BytesIO()
to_download = display_df.copy() if not filtered.empty else pd.DataFrame()
to_download.to_csv(csv_buf,index=False)
st.download_button("Download CSV", data=csv_buf.getvalue(), file_name="yougov_filtered.csv", mime="text/csv")
st.caption("Tip: upload a different Excel file with the same crosstab layout to analyze other policies or questions.")
