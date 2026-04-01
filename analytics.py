import streamlit as st
from supabase import create_client, Client
import pandas as pd
import altair as alt

# Connect to Supabase using secrets.toml
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase_client = init_connection()

# Initialize session state for interactive components
if 'selection' not in st.session_state:
    st.session_state['selection'] = None

# Define the fixed PM Fee
PM_FEE = 6000

# Fetch data from the 'live_dispatches' table in Supabase
def fetch_data():
    response = supabase_client.from_('live_dispatches').select("*").execute()
    data = response.data
    return pd.DataFrame(data)

# Set up the Streamlit app
st.set_page_config(page_title="Operations & Revenue Intelligence Dashboard", layout="wide")
st.title("Operations & Revenue Intelligence Dashboard")

dispatches_df = fetch_data()

# Define PM_FEE placeholder if not globally defined (to prevent errors in calculation)
if 'PM_FEE' not in locals() and 'PM_FEE' not in globals():
    PM_FEE = 0

if not dispatches_df.empty:
    # --- Pre-processing data for all sections ---
    dispatches_df['CheckInDate'] = pd.to_datetime(dispatches_df['CheckInDate'])

    dispatches_df['Multiplier'] = pd.to_numeric(dispatches_df.get('Multiplier', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Total DXC Pay'] = pd.to_numeric(dispatches_df.get('Total DXC Pay', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Total FN Pay'] = pd.to_numeric(dispatches_df.get('Total FN Pay', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Hours'] = pd.to_numeric(dispatches_df.get('Hours', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)

    dispatches_df['DXC_Cost_Calc'] = dispatches_df['Multiplier'] * dispatches_df['Total DXC Pay']
    dispatches_df['PNL'] = dispatches_df['DXC_Cost_Calc'] - dispatches_df['Total FN Pay']

    # --- Monthly Executive Summary Section ---
    with st.expander("### **Monthly Executive Summary**"):
        dispatches_df['month_year_str'] = dispatches_df['CheckInDate'].dt.to_period('M').astype(str)

        month_options = sorted(dispatches_df['month_year_str'].unique(), reverse=True)
        month_options_chronological = sorted(dispatches_df['month_year_str'].unique(), reverse=False)

        selected_month_str = st.selectbox("Select a Month", month_options)

        selected_month_df = dispatches_df[dispatches_df['month_year_str'] == selected_month_str].copy()

        total_dxc_cost = selected_month_df['DXC_Cost_Calc'].sum()
        total_billed = total_dxc_cost + 6000
        total_fn_pay = selected_month_df['Total FN Pay'].sum()
        profit_loss = total_dxc_cost - total_fn_pay
        profit_loss_with_fee = profit_loss + PM_FEE

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(label="Total Revenue", value=f"${total_billed:,.2f}")

        with col2:
            st.metric(label="Total Field Service Cost", value=f"${total_fn_pay:,.2f}")

        with col3:
            st.metric(label="Net Margin (incl. Management Fee)", value=f"${profit_loss_with_fee:,.2f}")

    st.markdown("---")

    # --- Revenue & Profitability Trends Section ---
    with st.expander("### **Revenue & Profitability Trends**"):

        monthly_summary_df = dispatches_df.groupby('month_year_str').agg(
            total_dxc_cost=('DXC_Cost_Calc', 'sum'),
            total_fn_pay=('Total FN Pay', 'sum')
        ).reset_index()

        monthly_summary_df['Total Revenue'] = monthly_summary_df['total_dxc_cost'] + 6000
        monthly_summary_df['Net Margin'] = monthly_summary_df['total_dxc_cost'] - monthly_summary_df['total_fn_pay']
        monthly_summary_df['Net Margin (incl. Management Fee)'] = monthly_summary_df['Net Margin'] + PM_FEE

        monthly_summary_df.rename(columns={'total_fn_pay': 'Total Field Service Cost'}, inplace=True)

        chart_data = monthly_summary_df.melt(
            id_vars=['month_year_str'],
            value_vars=['Total Revenue', 'Total Field Service Cost', 'Net Margin (incl. Management Fee)'],
            var_name='Metric',
            value_name='Value'
        )

        line_chart = alt.Chart(chart_data).mark_line().encode(
            x=alt.X('month_year_str', sort=month_options_chronological, title="Month"),
            y=alt.Y('Value', title="Amount ($)", axis=alt.Axis(format='$,.0f')),
            color='Metric',
            tooltip=['month_year_str', 'Metric', alt.Tooltip('Value', format='$,.2f')]
        )

        point_layer = alt.Chart(chart_data).mark_point(
            filled=True,
            size=100
        ).encode(
            x=alt.X('month_year_str', sort=month_options_chronological),
            y=alt.Y('Value'),
            color='Metric',
            tooltip=['month_year_str', 'Metric', alt.Tooltip('Value', format='$,.2f')]
        )

        final_chart = (line_chart + point_layer).properties(
            title='Revenue, Field Service Cost & Net Margin — Monthly Overview'
        ).interactive()

        st.altair_chart(final_chart, use_container_width=True)

    st.markdown("---")

    # --- Operational Performance Summary Section ---
    with st.expander("### **Operational Performance Summary**"):
        breakdown_month_options = sorted(dispatches_df['month_year_str'].unique(), reverse=True)
        selected_breakdown_month = st.selectbox("Select Month for Breakdown", breakdown_month_options, key='breakdown_month_selector')

        selected_breakdown_df = dispatches_df[dispatches_df['month_year_str'] == selected_breakdown_month].copy()

        col_tickets, col_avg_time, col_avg_pnl = st.columns(3)

        total_tickets = len(selected_breakdown_df)
        avg_time_to_close = selected_breakdown_df['Hours'].mean()
        avg_pnl_per_ticket = selected_breakdown_df['Adjusted_Profit'].mean()

        with col_tickets:
            st.metric(label="Total Dispatches", value=total_tickets)

        with col_avg_time:
            st.metric(label="Avg. Resolution Time", value=f"{avg_time_to_close:.2f} hrs")

        with col_avg_pnl:
            st.metric(label="Avg. Net Margin per Dispatch", value=f"${avg_pnl_per_ticket:,.2f}")

        st.markdown("---")

        st.subheader(f"Dispatch Volume by Location — {selected_breakdown_month}")

        tickets_per_site = selected_breakdown_df.groupby('Site').agg(
            total_dispatches=('CheckInDate', 'count')
        ).reset_index()

        bar_chart_site = alt.Chart(tickets_per_site).mark_bar().encode(
            x=alt.X('Site', title='Location', sort=None),
            y=alt.Y('total_dispatches', title='Total Dispatches'),
            tooltip=[
                alt.Tooltip('Site', title='Location'),
                alt.Tooltip('total_dispatches', title='Total Dispatches', format=',')
            ]
        ).properties(
            title=f'Dispatch Volume by Location — {selected_breakdown_month}'
        )
        st.altair_chart(bar_chart_site, use_container_width=True)

    st.markdown("---")

    # --- Key Performance Indicators Section ---
    with st.expander("### **Key Performance Indicators (KPIs)**"):
        monthly_data = dispatches_df.groupby(pd.Grouper(key='CheckInDate', freq='ME')).agg(
            total_dispatches=('CheckInDate', 'count'),
            total_dxc_cost=('DXC_Cost_Calc', 'sum'),
            total_fn_pay=('Total FN Pay', 'sum'),
            avg_hours=('Hours', 'mean'),
            avg_pnl_per_ticket=('Adjusted_Profit', 'mean')
        ).reset_index()

        monthly_data['profit_loss'] = monthly_data['total_dxc_cost'] - monthly_data['total_fn_pay']
        monthly_data['profit_loss_with_fee'] = monthly_data['profit_loss'] + PM_FEE
        monthly_data['month_label'] = monthly_data['CheckInDate'].dt.strftime('%m/%y')

        month_sort_order = monthly_data['month_label'].tolist()

        st.markdown("#### Monthly Dispatch Volume")

        tickets_chart = alt.Chart(monthly_data).mark_line(point=True, color='#1f77b4').encode(
            x=alt.X('month_label', sort=month_sort_order, axis=alt.Axis(title="Month", labelAngle=-45)),
            y=alt.Y('total_dispatches', title='Number of Dispatches', axis=alt.Axis(titleColor='#1f77b4')),
            tooltip=[
                alt.Tooltip('month_label', title='Month'),
                alt.Tooltip('total_dispatches', title='Total Dispatches', format=','),
            ]
        ).properties(
            title="Monthly Dispatch Volume"
        ).interactive()

        st.altair_chart(tickets_chart, use_container_width=True)

        st.markdown("#### Avg. Resolution Time")

        avg_time_chart = alt.Chart(monthly_data).mark_line(point=True, color='#9467bd').encode(
            x=alt.X('month_label', sort=month_sort_order, axis=alt.Axis(title="Month", labelAngle=-45)),
            y=alt.Y('avg_hours', title='Avg. Resolution Time (Hours)', axis=alt.Axis(titleColor='#9467bd')),
            tooltip=[
                alt.Tooltip('month_label', title='Month'),
                alt.Tooltip('avg_hours', title='Avg. Resolution Time', format='.2f'),
            ]
        ).properties(
            title="Monthly Avg. Resolution Time per Dispatch"
        ).interactive()

        st.altair_chart(avg_time_chart, use_container_width=True)

        st.markdown("#### Avg. Net Margin per Dispatch")

        avg_pnl_chart = alt.Chart(monthly_data).mark_line(point=True, color='#2ca02c').encode(
            x=alt.X('month_label', sort=month_sort_order, axis=alt.Axis(title="Month", labelAngle=-45)),
            y=alt.Y('avg_pnl_per_ticket', title='Avg. Net Margin per Dispatch ($)', axis=alt.Axis(titleColor='#2ca02c', format='$,.0f')),
            tooltip=[
                alt.Tooltip('month_label', title='Month'),
                alt.Tooltip('avg_pnl_per_ticket', title='Avg. Net Margin per Dispatch', format='$,.2f')
            ]
        ).properties(
            title="Monthly Avg. Net Margin per Dispatch"
        ).interactive()

        st.altair_chart(avg_pnl_chart, use_container_width=True)

    st.markdown("---")

    # --- Dispatch Volume by Location & Period ---
    with st.expander("### **Dispatch Volume by Location & Period**"):
        col_site, col_month = st.columns(2)

        with col_site:
            st.subheader("Per Location")
            tickets_per_site_per_month = dispatches_df.groupby(['Site', 'month_year_str']).agg(
                count=('CheckInDate', 'count')
            ).reset_index()

            avg_tickets_by_site = tickets_per_site_per_month.groupby('Site').agg(
                avg_dispatches=('count', 'mean')
            ).reset_index()

            bar_chart_site = alt.Chart(avg_tickets_by_site).mark_bar().encode(
                x=alt.X('Site', title='Location', sort=None),
                y=alt.Y('avg_dispatches', title='Avg. Monthly Dispatch Count'),
                tooltip=[
                    alt.Tooltip('Site', title='Location'),
                    alt.Tooltip('avg_dispatches', title='Avg. Dispatches', format='.2f')
                ]
            ).properties(
                title='Avg. Dispatch Count per Location (Monthly)'
            )
            st.altair_chart(bar_chart_site, use_container_width=True)

        with col_month:
            st.subheader("Per Period")
            tickets_by_month = dispatches_df.groupby('month_year_str').agg(
                count=('CheckInDate', 'count')
            ).reset_index()

            line_chart_month = alt.Chart(tickets_by_month).mark_line(point=True).encode(
                x=alt.X('month_year_str', title='Month', sort=None, axis=alt.Axis(labelAngle=-45)),
                y=alt.Y('count', title='Dispatch Count'),
                tooltip=[
                    alt.Tooltip('month_year_str', title='Month'),
                    alt.Tooltip('count', title='Dispatches', format=',')
                ]
            ).properties(
                title='Dispatch Count per Period'
            )
            st.altair_chart(line_chart_month, use_container_width=True)

    st.markdown("---")

    # --- Service Category & Location Analysis ---
    with st.expander("### **Service Category & Location Analysis**", expanded=True):
        col1, col2 = st.columns(2)

        filtered_tickets = dispatches_df.dropna(subset=['Subtype', 'Item'])

        breakdown_month_options = ['All Periods'] + sorted(filtered_tickets['month_year_str'].unique().tolist())
        selected_breakdown_month_pie = st.selectbox("Select a Period for Analysis", breakdown_month_options)

        if selected_breakdown_month_pie != 'All Periods':
            monthly_filtered_data = filtered_tickets[filtered_tickets['month_year_str'] == selected_breakdown_month_pie]
        else:
            monthly_filtered_data = filtered_tickets.copy()

        with col1:
            data_to_chart_subtype = monthly_filtered_data.groupby('Subtype').agg(
                count=('CheckInDate', 'count')
            ).reset_index()

            selection = alt.selection_point(
                fields=['Subtype'],
                on="click",
                name="selection"
            )

            base_pie_subtype = alt.Chart(data_to_chart_subtype).encode(
                theta=alt.Theta("count", stack=True),
                color=alt.Color("Subtype", title="Service Category"),
                order=alt.Order("count", sort="descending"),
                tooltip=[alt.Tooltip("Subtype", title="Service Category"), "count"]
            ).properties(
                title=f'Service Category Distribution — {selected_breakdown_month_pie}'
            )

            pie_chart_subtype = base_pie_subtype.mark_arc(outerRadius=120)
            combined_chart_subtype = pie_chart_subtype.add_params(selection)
            st.altair_chart(combined_chart_subtype, use_container_width=True)

            selected_subtype_from_chart = None
            if st.session_state and st.session_state.selection:
                selected_subtype_from_chart = st.session_state.selection.get('Subtype', [None])[0]

            subtype_options = ['All Service Categories'] + sorted(data_to_chart_subtype['Subtype'].unique().tolist())

            initial_index = 0
            if selected_subtype_from_chart and selected_subtype_from_chart in subtype_options:
                initial_index = subtype_options.index(selected_subtype_from_chart)

            selected_subtype = st.selectbox(
                "Select a Service Category to view Location Breakdown:",
                options=subtype_options,
                index=initial_index,
                key='subtype_select_box',
            )

        with col2:
            if selected_subtype != 'All Service Categories':
                filtered_by_subtype = monthly_filtered_data[monthly_filtered_data['Subtype'] == selected_subtype]

                if not filtered_by_subtype.empty:
                    site_breakdown = filtered_by_subtype.groupby('Site').agg(
                        count=('CheckInDate', 'count')
                    ).reset_index()

                    st.markdown(f'#### Location Breakdown — "{selected_subtype}" ({selected_breakdown_month_pie})')

                    bar_chart_site_breakdown = alt.Chart(site_breakdown).mark_bar().encode(
                        x=alt.X('Site', title='Location', sort='-y'),
                        y=alt.Y('count', title='Dispatch Count'),
                        tooltip=[
                            alt.Tooltip('Site', title='Location'),
                            alt.Tooltip('count', title='Dispatches', format=',')
                        ]
                    ).properties(
                        title=f'Location Distribution — "{selected_subtype}"'
                    )
                    st.altair_chart(bar_chart_site_breakdown, use_container_width=True)

                else:
                    st.info("No location data found for this service category.")
            else:
                st.info("Select a service category from the dropdown or the chart to view the Location Breakdown.")

else:
    st.warning("No data found in the `live_dispatches` table. Please check your database connection and table name.")




