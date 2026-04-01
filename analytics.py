import streamlit as st
from supabase import create_client, Client
import pandas as pd
import altair as alt
from datetime import datetime

# Connect to Supabase using secrets.toml
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase_client = init_connection()

if 'selection' not in st.session_state:
    st.session_state['selection'] = None

PM_FEE = 6000

# --- Professional Color Palette: Cool Corporate ---
COLOR_BLUE  = "#2563EB"
COLOR_TEAL  = "#0EA5E9"
COLOR_GRAY  = "#94A3B8"
COLOR_GREEN = "#10B981"
COLOR_AMBER = "#6366F1"
PALETTE     = [COLOR_BLUE, COLOR_TEAL, COLOR_AMBER, COLOR_GREEN, COLOR_GRAY]

# --- Top-level helper functions ---
def fetch_data():
    response = supabase_client.from_('live_dispatches').select("*").execute()
    return pd.DataFrame(response.data)

def delta(curr, prev):
    return curr - prev if prev is not None else None

def fmt_delta(val):
    if val is None:
        return None
    return f"-${abs(val):,.0f}" if val < 0 else f"${val:,.0f}"

def fmt_delta_2f(val):
    if val is None:
        return None
    return f"-${abs(val):,.2f}" if val < 0 else f"${val:,.2f}"

# --- Page Config ---
st.set_page_config(page_title="Operations & Revenue Intelligence Dashboard", layout="wide")

# --- Header ---
as_of = datetime.now().strftime("%B %d, %Y")
col_title, col_asof = st.columns([4, 1])
with col_title:
    st.title("Operations & Revenue Intelligence Dashboard")
with col_asof:
    st.markdown(f"<div style='text-align:right; padding-top:18px; color:{COLOR_GRAY}; font-size:13px;'>Data as of<br><strong>{as_of}</strong></div>", unsafe_allow_html=True)

st.markdown("---")

dispatches_df = fetch_data()

if not dispatches_df.empty:
    # --- Pre-processing ---
    dispatches_df['CheckInDate']    = pd.to_datetime(dispatches_df['CheckInDate'])
    dispatches_df['Multiplier']     = pd.to_numeric(dispatches_df.get('Multiplier',    pd.Series([0]*len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Total DXC Pay']  = pd.to_numeric(dispatches_df.get('Total DXC Pay', pd.Series([0]*len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Total FN Pay']   = pd.to_numeric(dispatches_df.get('Total FN Pay',  pd.Series([0]*len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Hours']          = pd.to_numeric(dispatches_df.get('Hours',         pd.Series([0]*len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['DXC_Cost_Calc']  = dispatches_df['Multiplier'] * dispatches_df['Total DXC Pay']
    dispatches_df['PNL']            = dispatches_df['DXC_Cost_Calc'] - dispatches_df['Total FN Pay']
    dispatches_df['month_year_str'] = dispatches_df['CheckInDate'].dt.to_period('M').astype(str)

    month_options               = sorted(dispatches_df['month_year_str'].unique(), reverse=True)
    month_options_chronological = sorted(dispatches_df['month_year_str'].unique(), reverse=False)

    # --- Top-Level KPI Summary Row ---
    latest_month   = month_options[0]
    previous_month = month_options[1] if len(month_options) > 1 else None

    latest_df = dispatches_df[dispatches_df['month_year_str'] == latest_month]
    prev_df   = dispatches_df[dispatches_df['month_year_str'] == previous_month] if previous_month else None

    def calc_metrics(df):
        dxc        = df['DXC_Cost_Calc'].sum()
        fn         = df['Total FN Pay'].sum()
        rev        = dxc + PM_FEE
        margin     = dxc - fn + PM_FEE
        dispatches = len(df)
        avg_res    = df['Hours'].mean()
        avg_margin = df['Adjusted_Profit'].mean() if 'Adjusted_Profit' in df.columns else 0
        return rev, fn, margin, dispatches, avg_res, avg_margin

    rev, fn, margin, dispatches, avg_res, avg_margin = calc_metrics(latest_df)
    if prev_df is not None:
        p_rev, p_fn, p_margin, p_dispatches, p_avg_res, p_avg_margin = calc_metrics(prev_df)
    else:
        p_rev = p_fn = p_margin = p_dispatches = p_avg_res = p_avg_margin = None

    st.markdown(f"#### Executive Summary — {latest_month}")
    st.caption("Month-over-month snapshot of top-line business performance. Deltas compare to the prior month.")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Revenue",               f"${rev:,.0f}",        delta=fmt_delta(delta(rev, p_rev)),              delta_color="normal")
    k2.metric("Total Field Service Cost",    f"${fn:,.0f}",         delta=fmt_delta(delta(fn, p_fn)),                delta_color="inverse")
    k3.metric("Net Margin (incl. Mgmt Fee)", f"${margin:,.0f}",     delta=fmt_delta(delta(margin, p_margin)),        delta_color="normal")
    k4.metric("Total Dispatches",            f"{dispatches:,}",     delta=str(delta(dispatches, p_dispatches))      if p_dispatches is not None else None, delta_color="normal")
    k5.metric("Avg. Resolution Time",        f"{avg_res:.1f} hrs",  delta=f"{delta(avg_res, p_avg_res):.1f} hrs"    if p_avg_res    is not None else None, delta_color="inverse")
    k6.metric("Avg. Net Margin / Dispatch",  f"${avg_margin:,.2f}", delta=fmt_delta(delta(avg_margin, p_avg_margin)), delta_color="normal")

    st.markdown("---")

    # --- Tabs ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Revenue & Profitability",
        "📋 Monthly Executive Summary",
        "📊 Operational Performance",
        "🔑 Key Performance Indicators",
        "🗂 Service Category Analysis"
    ])

    # ── Tab 1: Revenue & Profitability Trends ─────────────────────────────────
    with tab1:
        st.markdown("### Revenue & Profitability Trends")
        st.caption("Stacked view of Field Service Cost and Net Margin comprising Total Revenue, trended month over month.")

        monthly_summary_df = dispatches_df.groupby('month_year_str').agg(
            total_dxc_cost=('DXC_Cost_Calc', 'sum'),
            total_fn_pay=('Total FN Pay', 'sum')
        ).reset_index()
        monthly_summary_df['Total Revenue']                     = monthly_summary_df['total_dxc_cost'] + PM_FEE
        monthly_summary_df['Net Margin (incl. Management Fee)'] = monthly_summary_df['total_dxc_cost'] - monthly_summary_df['total_fn_pay'] + PM_FEE
        monthly_summary_df.rename(columns={'total_fn_pay': 'Total Field Service Cost'}, inplace=True)

        chart_data = monthly_summary_df.melt(
            id_vars=['month_year_str'],
            value_vars=['Total Field Service Cost', 'Net Margin (incl. Management Fee)'],
            var_name='Metric', value_name='Value'
        )

        stacked_bar = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('month_year_str', sort=month_options_chronological, title="Month",
                    axis=alt.Axis(labelAngle=-45, labelFontSize=12, titleFontSize=13)),
            y=alt.Y('Value', stack='zero', title="Total Revenue ($)",
                    axis=alt.Axis(format='$,.0f', labelFontSize=12, titleFontSize=13)),
            color=alt.Color('Metric', scale=alt.Scale(range=[COLOR_BLUE, COLOR_TEAL]),
                            legend=alt.Legend(title="Metric", labelFontSize=12, titleFontSize=13)),
            tooltip=['month_year_str', 'Metric', alt.Tooltip('Value', format='$,.2f')]
        ).properties(
            title=alt.TitleParams('Revenue, Field Service Cost & Net Margin — Monthly Overview',
                                  fontSize=16, fontWeight='bold'),
            height=400
        ).configure_view(strokeWidth=0).configure_axis(grid=False).interactive()

        st.altair_chart(stacked_bar, use_container_width=True)

        # Summary Insights
        latest_rev    = monthly_summary_df[monthly_summary_df['month_year_str'] == latest_month]['Total Revenue'].values
        prev_rev      = monthly_summary_df[monthly_summary_df['month_year_str'] == previous_month]['Total Revenue'].values if previous_month else None
        latest_margin = monthly_summary_df[monthly_summary_df['month_year_str'] == latest_month]['Net Margin (incl. Management Fee)'].values
        prev_margin   = monthly_summary_df[monthly_summary_df['month_year_str'] == previous_month]['Net Margin (incl. Management Fee)'].values if previous_month else None

        insights = []
        if latest_rev.size and prev_rev is not None and prev_rev.size:
            chg = latest_rev[0] - prev_rev[0]
            pct = (chg / prev_rev[0]) * 100
            direction = "up" if chg >= 0 else "down"
            insights.append(f"💰 Total Revenue is **{direction} {abs(pct):.1f}%** vs. prior month (${abs(chg):,.0f} {'increase' if chg >= 0 else 'decrease'}).")
        if latest_margin.size and prev_margin is not None and prev_margin.size:
            chg = latest_margin[0] - prev_margin[0]
            direction = "up" if chg >= 0 else "down"
            insights.append(f"📊 Net Margin is **{direction} ${abs(chg):,.0f}** vs. prior month.")
        if insights:
            st.markdown("**Summary Insights**")
            for i in insights:
                st.markdown(f"- {i}")

        # Data Table
        st.markdown("#### Monthly Revenue Detail")
        st.caption("Exact figures underlying the chart above.")
        display_df = monthly_summary_df[['month_year_str', 'Total Revenue', 'Total Field Service Cost', 'Net Margin (incl. Management Fee)']].copy()
        display_df.columns = ['Month', 'Total Revenue', 'Total Field Service Cost', 'Net Margin (incl. Mgmt Fee)']
        display_df = display_df.sort_values('Month', ascending=False)
        for col in ['Total Revenue', 'Total Field Service Cost', 'Net Margin (incl. Mgmt Fee)']:
            display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Tab 2: Monthly Executive Summary ──────────────────────────────────────
    with tab2:
        st.markdown("### Monthly Executive Summary")
        st.caption("Select a month to review top-line revenue, cost, and margin performance for that period.")

        selected_month_str = st.selectbox("Select a Month", month_options)
        selected_month_df  = dispatches_df[dispatches_df['month_year_str'] == selected_month_str].copy()
        prev_month_str     = month_options[month_options.index(selected_month_str) + 1] if month_options.index(selected_month_str) + 1 < len(month_options) else None
        prev_month_df      = dispatches_df[dispatches_df['month_year_str'] == prev_month_str].copy() if prev_month_str else None

        total_dxc_cost       = selected_month_df['DXC_Cost_Calc'].sum()
        total_billed         = total_dxc_cost + PM_FEE
        total_fn_pay         = selected_month_df['Total FN Pay'].sum()
        profit_loss_with_fee = total_dxc_cost - total_fn_pay + PM_FEE

        p_billed = (prev_month_df['DXC_Cost_Calc'].sum() + PM_FEE)                                                    if prev_month_df is not None else None
        p_fn     = prev_month_df['Total FN Pay'].sum()                                                                 if prev_month_df is not None else None
        p_pl     = (prev_month_df['DXC_Cost_Calc'].sum() - prev_month_df['Total FN Pay'].sum() + PM_FEE)              if prev_month_df is not None else None

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Revenue",               f"${total_billed:,.2f}",         delta=fmt_delta_2f(total_billed - p_billed)         if p_billed is not None else None, delta_color="normal")
        col2.metric("Total Field Service Cost",    f"${total_fn_pay:,.2f}",         delta=fmt_delta_2f(total_fn_pay - p_fn)             if p_fn     is not None else None, delta_color="inverse")
        col3.metric("Net Margin (incl. Mgmt Fee)", f"${profit_loss_with_fee:,.2f}", delta=fmt_delta_2f(profit_loss_with_fee - p_pl)     if p_pl     is not None else None, delta_color="normal")

    # ── Tab 3: Operational Performance ────────────────────────────────────────
    with tab3:
        st.markdown("### Operational Performance Summary")
        st.caption("Dispatch volume, resolution efficiency, and per-dispatch margin for the selected period.")

        selected_breakdown_month = st.selectbox("Select Month", month_options, key='breakdown_month_selector')
        selected_breakdown_df    = dispatches_df[dispatches_df['month_year_str'] == selected_breakdown_month].copy()
        prev_breakdown_str       = month_options[month_options.index(selected_breakdown_month) + 1] if month_options.index(selected_breakdown_month) + 1 < len(month_options) else None
        prev_breakdown_df        = dispatches_df[dispatches_df['month_year_str'] == prev_breakdown_str].copy() if prev_breakdown_str else None

        total_tix = len(selected_breakdown_df)
        avg_time  = selected_breakdown_df['Hours'].mean()
        avg_pnl   = selected_breakdown_df['Adjusted_Profit'].mean() if 'Adjusted_Profit' in selected_breakdown_df.columns else 0

        p_tix  = len(prev_breakdown_df)                                                                                if prev_breakdown_df is not None else None
        p_time = prev_breakdown_df['Hours'].mean()                                                                     if prev_breakdown_df is not None else None
        p_pnl  = prev_breakdown_df['Adjusted_Profit'].mean() if 'Adjusted_Profit' in prev_breakdown_df.columns else 0 if prev_breakdown_df is not None else None

        col_t, col_a, col_p = st.columns(3)
        col_t.metric("Total Dispatches",           f"{total_tix:,}",      delta=str(total_tix - p_tix)           if p_tix  is not None else None, delta_color="normal")
        col_a.metric("Avg. Resolution Time",       f"{avg_time:.2f} hrs", delta=f"{avg_time - p_time:.2f} hrs"   if p_time is not None else None, delta_color="inverse")
        col_p.metric("Avg. Net Margin / Dispatch", f"${avg_pnl:,.2f}",    delta=fmt_delta_2f(avg_pnl - p_pnl)   if p_pnl  is not None else None, delta_color="normal")

        st.markdown("---")
        st.subheader(f"Dispatch Volume by Location — {selected_breakdown_month}")

        tickets_per_site = selected_breakdown_df.groupby('Site').agg(
            total_dispatches=('CheckInDate', 'count')
        ).reset_index().sort_values('total_dispatches', ascending=False)

        bar_site = alt.Chart(tickets_per_site).mark_bar(color=COLOR_BLUE).encode(
            x=alt.X('Site', title='Location', sort='-y',
                    axis=alt.Axis(labelAngle=-45, labelFontSize=12, titleFontSize=13)),
            y=alt.Y('total_dispatches', title='Total Dispatches',
                    axis=alt.Axis(labelFontSize=12, titleFontSize=13)),
            tooltip=[alt.Tooltip('Site', title='Location'), alt.Tooltip('total_dispatches', title='Total Dispatches', format=',')]
        ).properties(
            title=alt.TitleParams(f'Dispatch Volume by Location — {selected_breakdown_month}', fontSize=16, fontWeight='bold'),
            height=350
        ).configure_view(strokeWidth=0).configure_axis(grid=False)
        st.altair_chart(bar_site, use_container_width=True)

    # ── Tab 4: Key Performance Indicators ─────────────────────────────────────
    with tab4:
        st.markdown("### Key Performance Indicators (KPIs)")
        st.caption("Longitudinal trends in dispatch volume, resolution efficiency, and per-dispatch margin across all periods.")

        monthly_data = dispatches_df.groupby(pd.Grouper(key='CheckInDate', freq='ME')).agg(
            total_dispatches=('CheckInDate', 'count'),
            total_dxc_cost=('DXC_Cost_Calc', 'sum'),
            total_fn_pay=('Total FN Pay', 'sum'),
            avg_hours=('Hours', 'mean'),
            avg_pnl_per_ticket=('Adjusted_Profit', 'mean')
        ).reset_index()
        monthly_data['month_label'] = monthly_data['CheckInDate'].dt.strftime('%m/%y')
        sort_order = monthly_data['month_label'].tolist()

        def kpi_line(data, y_field, y_title, color, fmt=None):
            enc_y = alt.Y(y_field, title=y_title,
                          axis=alt.Axis(titleColor=color, labelFontSize=12, titleFontSize=13,
                                        format=fmt if fmt else alt.Undefined))
            return (
                alt.Chart(data).mark_line(point=True, color=color).encode(
                    x=alt.X('month_label', sort=sort_order, axis=alt.Axis(title="Month", labelAngle=-45, labelFontSize=12, titleFontSize=13)),
                    y=enc_y,
                    tooltip=[alt.Tooltip('month_label', title='Month'), alt.Tooltip(y_field, format=fmt if fmt else '.2f')]
                ).properties(height=300).configure_view(strokeWidth=0).configure_axis(grid=False).interactive()
            )

        st.markdown("#### Monthly Dispatch Volume")
        st.altair_chart(kpi_line(monthly_data, 'total_dispatches', 'Number of Dispatches', COLOR_BLUE), use_container_width=True)

        st.markdown("#### Avg. Resolution Time")
        st.altair_chart(kpi_line(monthly_data, 'avg_hours', 'Avg. Resolution Time (Hours)', COLOR_TEAL), use_container_width=True)

        st.markdown("#### Avg. Net Margin per Dispatch")
        st.altair_chart(kpi_line(monthly_data, 'avg_pnl_per_ticket', 'Avg. Net Margin per Dispatch ($)', COLOR_GREEN, fmt='$,.0f'), use_container_width=True)

    # ── Tab 5: Service Category & Location Analysis ────────────────────────────
    with tab5:
        st.markdown("### Service Category & Location Analysis")
        st.caption("Breakdown of dispatch volume by service category and location. Select a category to drill into its location distribution.")

        filtered_tickets = dispatches_df.dropna(subset=['Subtype', 'Item'])
        period_options   = ['All Periods'] + sorted(filtered_tickets['month_year_str'].unique().tolist())
        selected_period  = st.selectbox("Select a Period for Analysis", period_options)

        monthly_filtered_data = filtered_tickets if selected_period == 'All Periods' else filtered_tickets[filtered_tickets['month_year_str'] == selected_period].copy()

        col1, col2 = st.columns(2)

        with col1:
            data_subtype = monthly_filtered_data.groupby('Subtype').agg(count=('CheckInDate', 'count')).reset_index()

            selection = alt.selection_point(fields=['Subtype'], on="click", name="selection")

            pie = alt.Chart(data_subtype).mark_arc(outerRadius=120).encode(
                theta=alt.Theta("count", stack=True),
                color=alt.Color("Subtype", title="Service Category",
                                scale=alt.Scale(range=PALETTE),
                                legend=alt.Legend(labelFontSize=12, titleFontSize=13)),
                order=alt.Order("count", sort="descending"),
                tooltip=[alt.Tooltip("Subtype", title="Service Category"), "count"]
            ).properties(
                title=alt.TitleParams(f'Service Category Distribution — {selected_period}', fontSize=16, fontWeight='bold')
            ).add_params(selection)

            st.altair_chart(pie, use_container_width=True)

            selected_subtype_from_chart = None
            if st.session_state and st.session_state.selection:
                selected_subtype_from_chart = st.session_state.selection.get('Subtype', [None])[0]

            subtype_options = ['All Service Categories'] + sorted(data_subtype['Subtype'].unique().tolist())
            initial_index   = subtype_options.index(selected_subtype_from_chart) if selected_subtype_from_chart in subtype_options else 0

            selected_subtype = st.selectbox("Select a Service Category to view Location Breakdown:",
                                            options=subtype_options, index=initial_index, key='subtype_select_box')

        with col2:
            if selected_subtype != 'All Service Categories':
                filtered_by_subtype = monthly_filtered_data[monthly_filtered_data['Subtype'] == selected_subtype]
                if not filtered_by_subtype.empty:
                    site_breakdown = filtered_by_subtype.groupby('Site').agg(count=('CheckInDate', 'count')).reset_index().sort_values('count', ascending=False)
                    st.markdown(f'#### Location Distribution — "{selected_subtype}" ({selected_period})')
                    bar_breakdown = alt.Chart(site_breakdown).mark_bar(color=COLOR_TEAL).encode(
                        x=alt.X('Site', title='Location', sort='-y',
                                axis=alt.Axis(labelAngle=-45, labelFontSize=12, titleFontSize=13)),
                        y=alt.Y('count', title='Dispatch Count',
                                axis=alt.Axis(labelFontSize=12, titleFontSize=13)),
                        tooltip=[alt.Tooltip('Site', title='Location'), alt.Tooltip('count', title='Dispatches', format=',')]
                    ).properties(
                        title=alt.TitleParams(f'Location Distribution — "{selected_subtype}"', fontSize=16, fontWeight='bold'),
                        height=350
                    ).configure_view(strokeWidth=0).configure_axis(grid=False)
                    st.altair_chart(bar_breakdown, use_container_width=True)
                else:
                    st.info("No location data found for this service category.")
            else:
                st.info("Select a service category from the dropdown or the chart to view the Location Breakdown.")

else:
    st.warning("No data found in the `live_dispatches` table. Please check your database connection and table name.")
