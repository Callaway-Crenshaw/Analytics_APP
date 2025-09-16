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
st.set_page_config(page_title="Analytics Dashboard", layout="wide")
st.title("Analytics Reporting Dashboard 📊")

# Fetch data once
dispatches_df = fetch_data()

if not dispatches_df.empty:
    # --- Pre-processing data for all sections ---
    # Convert CheckInDate to datetime and extract month/year
    dispatches_df['CheckInDate'] = pd.to_datetime(dispatches_df['CheckInDate'])
    
    # Ensure numeric columns exist and fill NaNs
    dispatches_df['Multiplier'] = pd.to_numeric(dispatches_df.get('Multiplier', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Total DXC Pay'] = pd.to_numeric(dispatches_df.get('Total DXC Pay', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Total FN Pay'] = pd.to_numeric(dispatches_df.get('Total FN Pay', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    dispatches_df['Hours'] = pd.to_numeric(dispatches_df.get('Hours', pd.Series([0] * len(dispatches_df))), errors='coerce').fillna(0)
    
    # Calculate DXC_Cost_Calc and PNL for the entire DataFrame
    dispatches_df['DXC_Cost_Calc'] = dispatches_df['Multiplier'] * dispatches_df['Total DXC Pay']
    # Corrected PNL calculation to be on a per-ticket basis
    dispatches_df['PNL'] = dispatches_df['DXC_Cost_Calc'] - dispatches_df['Total FN Pay']

    # --- Month at a Glance Section ---
    with st.expander("### **Month at a Glance**"):
        # Create month_year for the dropdown and for grouping
        dispatches_df['month_year_str'] = dispatches_df['CheckInDate'].dt.to_period('M').astype(str)
        
        # Get a list of unique months to show in the dropdown, sorted
        month_options = sorted(dispatches_df['month_year_str'].unique(), reverse=True)
        selected_month_str = st.selectbox("Select a Month", month_options)
        
        # Filter the dataframe for the selected month
        selected_month_df = dispatches_df[dispatches_df['month_year_str'] == selected_month_str].copy()
        
        # Calculate metrics for the selected month
        total_dxc_cost = selected_month_df['DXC_Cost_Calc'].sum()
        total_fn_pay = selected_month_df['Total FN Pay'].sum()
        profit_loss = total_dxc_cost - total_fn_pay
        profit_loss_with_fee = profit_loss + PM_FEE
        
        # Display the metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(label="Total DXC Cost:", value=f"${total_dxc_cost:,.2f}")
        
        with col2:
            st.metric(label="Total FN Pay:", value=f"${total_fn_pay:,.2f}")
        
        with col3:
            st.metric(label="Profit/Loss:", value=f"${profit_loss:,.2f}")
        
        with col4:
            st.metric(label="Profit/Loss + PM Fee:", value=f"${profit_loss_with_fee:,.2f}")

    st.markdown("---")

    # --- Monthly Breakdown Section with Month Selector and Bar Chart ---
    with st.expander("### **Monthly Breakdown**"):
        # Create a separate month selector for this section
        breakdown_month_options = sorted(dispatches_df['month_year_str'].unique(), reverse=True)
        selected_breakdown_month = st.selectbox("Select Month for Breakdown", breakdown_month_options, key='breakdown_month_selector')
        
        # Filter the dataframe based on the new selector
        selected_breakdown_df = dispatches_df[dispatches_df['month_year_str'] == selected_breakdown_month].copy()

        # Display Metrics
        col_tickets, col_avg_time, col_avg_pnl = st.columns(3)
        
        # 1. Total Tickets for the month
        total_tickets = len(selected_breakdown_df)
        
        # 2. Average Time to Close
        avg_time_to_close = selected_breakdown_df['Hours'].mean()
        
        # 3. Average Profit/Loss per Ticket
        avg_pnl_per_ticket = selected_breakdown_df['PNL'].mean()
        
        # Display the metrics
        with col_tickets:
            st.metric(label="Total Tickets", value=total_tickets)
        
        with col_avg_time:
            st.metric(label="Avg Time to Close", value=f"{avg_time_to_close:.2f} hrs")

        with col_avg_pnl:
            st.metric(label="Avg P/L per Ticket", value=f"${avg_pnl_per_ticket:,.2f}")
        
        st.markdown("---")
        
        # --- Bar Chart: Tickets per Site for the selected month ---
        st.subheader(f"Tickets Per Site for {selected_breakdown_month}")
        
        # Calculate tickets per site
        tickets_per_site = selected_breakdown_df.groupby('Site').agg(
            total_tickets=('CheckInDate', 'count')
        ).reset_index()

        # Create the bar chart
        bar_chart_site = alt.Chart(tickets_per_site).mark_bar().encode(
            x=alt.X('Site', title='Site', sort=None),
            y=alt.Y('total_tickets', title='Total Tickets'),
            tooltip=[
                alt.Tooltip('Site', title='Site'),
                alt.Tooltip('total_tickets', title='Total Tickets', format=',')
            ]
        ).properties(
            title=f'Tickets Per Site in {selected_breakdown_month}'
        )
        st.altair_chart(bar_chart_site, use_container_width=True)
    
    st.markdown("---")
    
    # --- Monthly Trend Analysis with dynamic chart layering ---
    with st.expander("### **Monthly Trend Analysis**"):
        # Get data ready for trend analysis
        monthly_data = dispatches_df.groupby(pd.Grouper(key='CheckInDate', freq='ME')).agg(
            total_tickets=('CheckInDate', 'count'),
            total_dxc_cost=('DXC_Cost_Calc', 'sum'),
            total_fn_pay=('Total FN Pay', 'sum'),
            avg_hours=('Hours', 'mean'),
            avg_pnl_per_ticket=('PNL', 'mean')
        ).reset_index()

        # Calculate monthly profit/loss
        monthly_data['profit_loss'] = monthly_data['total_dxc_cost'] - monthly_data['total_fn_pay']
        monthly_data['profit_loss_with_fee'] = monthly_data['profit_loss'] + PM_FEE
        
        # Add a new column with formatted month/year string for the x-axis labels
        monthly_data['month_label'] = monthly_data['CheckInDate'].dt.strftime('%m/%y')

        # New radio button for chart options
        chart_selection = st.radio(
            "Select a Trend Chart to view:", 
            ("Count & Total Money", "Average & Efficiency"), 
            horizontal=True
        )
        
        if chart_selection == "Count & Total Money":
            # Create the first dual-axis chart for Tickets vs Total P/L
            tickets_line = alt.Chart(monthly_data).mark_line(point=True, color='blue').encode(
                x=alt.X('month_label', axis=alt.Axis(title=None, labelAngle=-45)),
                y=alt.Y('total_tickets', title='Number of Tickets', axis=alt.Axis(titleColor='blue')),
                tooltip=[
                    alt.Tooltip('month_label', title='Month'),
                    alt.Tooltip('total_tickets', title='Total Tickets', format=','),
                    alt.Tooltip('profit_loss_with_fee', title='Profit/Loss', format='$,.2f')
                ]
            )
            
            # Melt the data for the total P/L chart
            total_pnl_data = monthly_data.melt(
                id_vars=['month_label'], 
                value_vars=['profit_loss', 'profit_loss_with_fee'],
                var_name='Metric',
                value_name='Value'
            )
            total_pnl_chart = alt.Chart(total_pnl_data).mark_line(point=True).encode(
                x=alt.X('month_label', axis=alt.Axis(title=None, labelAngle=-45)),
                y=alt.Y('Value', title='Total P/L ($)', axis=alt.Axis(titleColor='orange')),
                color=alt.Color('Metric', title='Metric', scale=alt.Scale(range=['orange', 'red'])),
                tooltip=[
                    alt.Tooltip('month_label', title='Month'),
                    alt.Tooltip('Value', title='Amount', format='$,.2f')
                ]
            )

            combined_chart = alt.layer(tickets_line, total_pnl_chart).resolve_scale(y='independent')
            st.altair_chart(combined_chart, use_container_width=True)

        elif chart_selection == "Average & Efficiency":
            # Create the second dual-axis chart for Avg Time vs Avg P/L
            avg_time_chart = alt.Chart(monthly_data).mark_line(point=True, color='purple').encode(
                x=alt.X('month_label', axis=alt.Axis(title=None, labelAngle=-45)),
                y=alt.Y('avg_hours', title='Avg. Time (hrs)', axis=alt.Axis(titleColor='purple', titlePadding=20, labelPadding=5)),
                tooltip=[
                    alt.Tooltip('month_label', title='Month'),
                    alt.Tooltip('avg_hours', title='Avg. Time', format='.2f'),
                    alt.Tooltip('avg_pnl_per_ticket', title='Avg P/L per Ticket', format='$,.2f')
                ]
            )
            
            avg_pnl_chart = alt.Chart(monthly_data).mark_line(point=True, color='green').encode(
                x=alt.X('month_label', axis=alt.Axis(title=None, labelAngle=-45)),
                y=alt.Y('avg_pnl_per_ticket', title='Avg. P/L per Ticket ($)', axis=alt.Axis(titleColor='green', titlePadding=20, labelPadding=5)),
                tooltip=[
                    alt.Tooltip('month_label', title='Month'),
                    alt.Tooltip('avg_hours', title='Avg. Time', format='.2f'),
                    alt.Tooltip('avg_pnl_per_ticket', title='Avg P/L per Ticket', format='$,.2f')
                ]
            )
            
            combined_chart = alt.layer(avg_time_chart, avg_pnl_chart).resolve_scale(y='independent')
            st.altair_chart(combined_chart, use_container_width=True)

    st.markdown("---")

    # --- Bar Chart: Average Ticket Count per Site ---
    with st.expander("### **Average Ticket Count per Site**"):
        # Calculate average tickets by site
        avg_tickets_by_site = dispatches_df.groupby('Site').agg(
            avg_tickets=('CheckInDate', 'count')
        ).reset_index()

        # Create the new bar chart
        bar_chart_site = alt.Chart(avg_tickets_by_site).mark_bar().encode(
            x=alt.X('Site', title='Site', sort=None),
            y=alt.Y('avg_tickets', title='Average Ticket Count'),
            tooltip=[
                alt.Tooltip('Site', title='Site'),
                alt.Tooltip('avg_tickets', title='Average Tickets', format='.2f')
            ]
        ).properties(
            title='Average Ticket Count per Site'
        )
        
        st.altair_chart(bar_chart_site, use_container_width=True)
    
    st.markdown("---")

    # --- Pie Chart: Subtype & Site Breakdown ---
    with st.expander("### **Subtype & Site Breakdown**", expanded=True):
        col1, col2 = st.columns(2)

        # Drop null values for Subtype
        filtered_tickets = dispatches_df.dropna(subset=['Subtype', 'Item'])
        
        # Add a dropdown to select month for the breakdown charts
        breakdown_month_options = ['All Tickets'] + sorted(filtered_tickets['month_year_str'].unique().tolist())
        selected_breakdown_month_pie = st.selectbox("Select a Month for Breakdown", breakdown_month_options)

        # Filter data based on month selection for breakdown charts
        if selected_breakdown_month_pie != 'All Tickets':
            monthly_filtered_data = filtered_tickets[filtered_tickets['month_year_str'] == selected_breakdown_month_pie]
        else:
            monthly_filtered_data = filtered_tickets.copy()

        # --- LEFT COLUMN: Interactive Subtype Breakdown Chart ---
        with col1:
            data_to_chart_subtype = monthly_filtered_data.groupby('Subtype').agg(
                count=('CheckInDate', 'count')
            ).reset_index()
            
            # Create a selection that can be clicked on the chart
            selection = alt.selection_point(
                fields=['Subtype'],
                on="click",
                name="selection"
            )

            # Create the base pie chart
            base_pie_subtype = alt.Chart(data_to_chart_subtype).encode(
                theta=alt.Theta("count", stack=True),
                color=alt.Color("Subtype"),
                order=alt.Order("count", sort="descending"),
                tooltip=["Subtype", "count"]
            ).properties(
                title=f'Ticket Breakdown by Subtype for {selected_breakdown_month_pie}'
            )

            # Pie chart with selection
            pie_chart_subtype = base_pie_subtype.mark_arc(outerRadius=120)
            
            # Final combined chart with interactive selection
            combined_chart_subtype = pie_chart_subtype.add_params(selection)
            
            st.altair_chart(combined_chart_subtype, use_container_width=True)
            
            # Retrieve the selection from the chart
            selected_subtype_from_chart = None
            if st.session_state and st.session_state.selection:
                selected_subtype_from_chart = st.session_state.selection.get('Subtype', [None])[0]
            
            # Get the list of subtype options for the dropdown
            subtype_options = ['All Subtypes'] + sorted(data_to_chart_subtype['Subtype'].unique().tolist())
            
            # Determine the initial value for the selectbox
            initial_index = 0
            if selected_subtype_from_chart and selected_subtype_from_chart in subtype_options:
                initial_index = subtype_options.index(selected_subtype_from_chart)
            
            # Use the selected subtype from either the dropdown or the chart click
            selected_subtype = st.selectbox(
                "Select a Subtype to view Site Breakdown:",
                options=subtype_options,
                index=initial_index,
                key='subtype_select_box',
            )


        # --- RIGHT COLUMN: Site Breakdown Table ---
        with col2:
            if selected_subtype != 'All Subtypes':
                # Filter data for the selected subtype
                filtered_by_subtype = monthly_filtered_data[monthly_filtered_data['Subtype'] == selected_subtype]
                
                if not filtered_by_subtype.empty:
                    # Group by site and count tickets for the selected subtype
                    site_breakdown = filtered_by_subtype.groupby('Site').agg(
                        count=('CheckInDate', 'count')
                    ).reset_index()

                    st.markdown(f'#### Site Breakdown for "{selected_subtype}" ({selected_breakdown_month_pie})')
                    st.dataframe(site_breakdown, use_container_width=True, hide_index=True)
                else:
                    st.info("No site data found for this subtype.")
            else:
                st.info("Select a subtype from the dropdown or the pie chart to view the Site Breakdown.")

else:
    st.warning("No data found in the `live_dispatches` table. Please check your database connection and table name.")