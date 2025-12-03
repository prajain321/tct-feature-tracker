from datetime import datetime
from typing import Dict, Any
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode

from common import get_rocm_unique_value, get_rocm_versions
from packages.balancer import balance, force_refetch_and_update, comments_addition, update_effort
from packages.ticketfetchers.ticket_fetcher_optimized import TicketFetch

# Constants
JIRA_BASE_URL = "https://ontrack-internal.amd.com/browse/"
EFFORT_SIZES = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']

# Page configuration
st.set_page_config(
    page_title="Task Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
    <style>
    .main > div { padding-top: 2rem; }
    h1 { color: #1f77b4; font-weight: 600; margin-bottom: 2rem; }
    .stAlert { margin-top: 1rem; }
    .release-section {
        padding: 1rem;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-bottom: 2rem;
        background-color: #f8f9fa;
    }
    .release-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .block-container { padding-top: 1rem; }
    div[data-testid="stVerticalBlock"] > div:has(> div.element-container) { gap: 0rem; }
    .metric-card {
        background: white;
        padding: 1rem;
        min-height: 18.6rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin: 0.5rem;
        min-width: 150px;
        flex: 1 1 200px;
    }
    .metric-title {
        font-size: 1.2rem;
        color: black;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }
    .metric-value {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1f77b4;
    }
    .metrics-container {
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-bottom: 1rem;
    }
    .clickable-metric {
        cursor: pointer;
        transition: all 0.2s ease;
        padding: 6px 8px;
        border-radius: 4px;
        margin: 2px 0;
        position: relative;
    }
    .clickable-metric:hover {
        background-color: #e3f2fd;
        transform: translateX(2px);
    }
    .clickable-metric.active {
        background-color: #1f77b4;
    }
    .clickable-metric.active .metric-label {
        color: white !important;
    }
    .clickable-metric.active .metric-count {
        color: white !important;
    }
    .filter-badge {
        display: inline-block;
        padding: 6px 12px;
        background-color: #1f77b4;
        color: white;
        border-radius: 16px;
        font-size: 0.9rem;
        font-weight: 600;
        margin-right: 8px;
    }
    .st-emotion-cache-8atqhb .st-emotion-cache-1anq8dj{
        background-color: white;
        color: black;
        font-weight: 800;
        border: none;
    }
    .stTooltipIcon .st-emotion-cache-1anq8dj{
        background-color: rgb(19, 23, 32);
        color: inherit;
    }
    .st-emotion-cache-8atqhb .st-emotion-cache-1anq8dj:hover{
        background-color: #4fa3dd;
        color: white;
    }
    .stTooltipIcon .st-emotion-cache-1anq8dj:hover{
        background-color: rgba(250, 250, 250, 0.1);
        color: inherit;
    }
    .st-emotion-cache-1krtkoa{
        background-color: #1f77b4;
        color: white;
        font-weight: 800;
        border: none
    }
    </style>
""", unsafe_allow_html=True)


def format_qa_task_key(qa_task: str) -> str:
    """Format QA task key for API calls."""
    return f"|{qa_task}" if "SWDEV" in qa_task else ""


def get_ticket_id(feature_id: str, qa_task: str) -> str:
    """Construct full ticket ID from feature ID and QA task."""
    return f"{feature_id}{format_qa_task_key(qa_task)}"


def load_data(release: str, unique_key: int) -> pd.DataFrame:
    """Load data with caching."""
    try:
        with st.spinner(f"⏳ Loading data for {release}..."):
            data = balance(rocm_version=release, unique_key=str(unique_key))
            return pd.DataFrame(data)
    except Exception:  # pylint: disable=broad-except
        st.warning(f"⚠️ No Tickets Found for {release}")
        return pd.DataFrame()


def load_data_no_cache(release: str, unique_key: int) -> pd.DataFrame:
    """Load fresh data from server without caching."""
    try:
        tf = TicketFetch(max_workers=6, verbose=True,
                         rocm_version=release, unique_key=str(unique_key))
        force_refetch_and_update(rocm_version=release,
                                 unique_key=str(unique_key))
        return tf.fetch_tickets()
    except Exception:  # pylint: disable=broad-except
        st.warning(f"⚠️ No Tickets Found for {release}")
        return pd.DataFrame()


def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to CSV bytes."""
    return df.to_csv(index=False).encode('utf-8')


def initialize_filter_state(release: str):
    """Initialize filter state for a release."""
    filter_key = f"filter_{release}"
    if filter_key not in st.session_state:
        st.session_state[filter_key] = {
            'type': None,  # 'status', 'assignee', 'effort'
            'value': None,
            'column': None
        }


def set_filter(release: str, filter_type: str, value: str, column: str):
    """Set active filter for a release."""
    filter_key = f"filter_{release}"
    current_filter = st.session_state[filter_key]

    # Toggle filter if clicking same value
    if current_filter['type'] == filter_type and current_filter['value'] == value:
        st.session_state[filter_key] = {
            'type': None, 'value': None, 'column': None}
    else:
        st.session_state[filter_key] = {
            'type': filter_type,
            'value': value,
            'column': column
        }


def clear_filter(release: str):
    """Clear active filter for a release."""
    filter_key = f"filter_{release}"
    st.session_state[filter_key] = {
        'type': None, 'value': None, 'column': None}


def apply_filter(df: pd.DataFrame, release: str) -> pd.DataFrame:
    """Apply active filter to DataFrame."""
    filter_key = f"filter_{release}"
    if filter_key not in st.session_state:
        return df

    active_filter = st.session_state[filter_key]

    if active_filter['type'] and active_filter['value'] and active_filter['column']:
        column = active_filter['column']
        value = active_filter['value']

        if column in df.columns:
            # For assignee filter with non-implemented status
            if active_filter['type'] == 'assignee':
                return df[(df[column] == value) & (df['QA_status'] != 'Implemented')]
            else:
                return df[df[column] == value]

    return df


def create_clickable_html_component(release: str, items: list, filter_type: str, column: str, active_filter: dict):
    """Create HTML component with JavaScript to handle clicks directly."""

    rows_html = []
    for label, count, extra_info in items:
        is_active = (active_filter['type'] ==
                     filter_type and active_filter['value'] == label)
        active_class = 'active' if is_active else ''
        safe_label = label.replace("'", "\\'")

        rows_html.append(f"""
            <div class="clickable-metric {active_class}"
                 onclick="handleMetricClick('{release}', '{filter_type}', '{safe_label}', '{column}')">
                <div class="metric-label" style="font-size: 0.9rem; color: black; font-weight:800">{label}</div>
                <div class="metric-count" style="font-size: 1.2rem; font-weight: 600; color: #1f77b4;">{count} {extra_info}</div>
            </div>""")

    html_content = f"""
        <div class="metric-card">
            {"".join(rows_html)}
        </div>
        <script>
            function handleMetricClick(release, filterType, value, column) {{
                // Send message to parent Streamlit window
                window.parent.postMessage({{
                    type: 'streamlit:setComponentValue',
                    data: {{
                        release: release,
                        filterType: filterType,
                        value: value,
                        column: column
                    }}
                }}, '*');
            }}
        </script>
    """

    return components.html(html_content, height=320)


def render_analytics_section(df: pd.DataFrame, release: str):
    """Render analytics section with metrics and charts."""

    initialize_filter_state(release)
    filter_key = f"filter_{release}"
    active_filter = st.session_state[filter_key]

    # Show active filter badge and clear button
    if active_filter['type']:
        filter_col1, filter_col2 = st.columns([3, 1])
        with filter_col1:
            st.markdown(
                f'<span class="filter-badge">🔍 Filtered by: {active_filter["value"]}</span>',
                unsafe_allow_html=True
            )
        with filter_col2:
            if st.button("✖ Clear Filter", key=f"clear_filter_{release}"):
                clear_filter(release)
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    # Create three columns for the three metric cards
    col1, col2, col3, col4 = st.columns(4)

    # Use original unfiltered data for all counts
    original_df = load_data(
        release=release, unique_key=get_rocm_unique_value(release))

    # Status Analytics
    with col1:
        st.markdown("**Feature Status**")
        with st.container(height=240):
            if 'Feature_status' in df.columns:
                status_counts = original_df['Feature_status'].value_counts()

                for idx, (status, count) in enumerate(status_counts.items(), 1):
                    percentage = (count / len(original_df) * 100)
                    is_active = (
                        active_filter['type'] == 'status' and active_filter['value'] == status)

                    button_label = f"{status}: {count} ({percentage:.1f}%)"
                    button_type = "primary" if is_active else "secondary"

                    if st.button(button_label, key=f"status_{release}_{idx}",
                                 type=button_type, use_container_width=True):
                        set_filter(release, 'status', status, 'Feature_status')
                        st.rerun()
            else:
                st.info("Feature_status column not found")

    # Assignee Analytics
    with col2:
        st.markdown("**QA Assignee (Non-Implemented)**")
        with st.container(height=240):
            if 'QA_assignee' in df.columns and 'QA_status' in df.columns:
                non_implemented = original_df[original_df['QA_status']
                                              != 'Implemented']
                assignee_counts = non_implemented['QA_assignee'].value_counts()

                if len(assignee_counts) > 0:
                    for idx, (assignee, count) in enumerate(assignee_counts.items(), 1):
                        is_active = (
                            active_filter['type'] == 'assignee' and active_filter['value'] == assignee)

                        button_label = f"{assignee}: {count}"
                        button_type = "primary" if is_active else "secondary"

                        if st.button(button_label, key=f"assignee_{release}_{idx}",
                                     type=button_type, use_container_width=True):
                            set_filter(release, 'assignee',
                                       assignee, 'QA_assignee')
                            st.rerun()
                else:
                    st.success("✅ All tickets implemented!")
            else:
                st.info("Column not found")

    # Effort Size Analytics
    with col4:
        st.markdown("**Effort Size**")
        with st.container(height=240):
            if 'Effort' in df.columns:
                effort_counts = original_df['Effort'].value_counts()
                effort_counts = effort_counts.reindex(
                    EFFORT_SIZES, fill_value=0)

                btn_idx = 1
                for effort, count in effort_counts.items():
                    if count > 0:
                        percentage = (count / len(original_df) * 100)
                        is_active = (
                            active_filter['type'] == 'effort' and active_filter['value'] == effort)

                        button_label = f"{effort}: {count} ({percentage:.1f}%)"
                        button_type = "primary" if is_active else "secondary"

                        if st.button(button_label, key=f"effort_{release}_{btn_idx}",
                                     type=button_type, use_container_width=True):
                            set_filter(release, 'effort', effort, 'Effort')
                            st.rerun()
                        btn_idx += 1

                if btn_idx == 1:
                    st.info("No effort data available")
            else:
                st.info("Effort column not found")

    with col3:
        st.markdown("**QA Assignee (Implemented)**")
        # Remove the outer container - it's not needed
        with st.container(height=240):  # scrolling is automatic when height is set
            if 'QA_assignee' in df.columns and 'QA_status' in df.columns:
                implemented = df[df['QA_status'] == 'Implemented']
                assignee_counts = implemented['QA_assignee'].value_counts()

                if len(assignee_counts) > 0:
                    for idx, (assignee, count) in enumerate(assignee_counts.items(), 1):
                        is_active = (active_filter['type'] == 'assignee_impl' and
                                     active_filter['value'] == assignee)

                        button_label = f"{assignee}: {count}"
                        button_type = "primary" if is_active else "secondary"

                        if st.button(button_label,
                                     key=f"assignee_impl_{release}_{assignee}_{idx}",
                                     type=button_type,
                                     use_container_width=True):
                            set_filter(release, 'assignee_impl',
                                       assignee, 'QA_assignee')
                            st.rerun()
                else:
                    st.success("✅ All tickets implemented!")
            else:
                st.info("Column not found")

    st.divider()


def get_cell_renderers() -> Dict[str, JsCode]:
    """Get JavaScript cell renderers for AgGrid."""
    url_renderer = JsCode("""
    class UrlCellRenderer {
        init(params) {
            this.eGui = document.createElement('span');

            if (params.value === 'NA' || !params.value) {
                this.eGui.innerText = params.value || '';
            } else {
                const link = document.createElement('a');
                link.innerText = params.value;
                link.setAttribute('href', 'https://ontrack-internal.amd.com/browse/' + params.value);
                link.setAttribute('style', "text-decoration:none");
                link.setAttribute('target', "_blank");
                this.eGui.appendChild(link);
            }
        }
        getGui() { return this.eGui; }
    }
    """)

    comments_renderer = JsCode("""
    class CommentsCellRenderer {
        init(params) {
            this.eGui = document.createElement('div');
            this.eGui.innerHTML = params.value || '';
            this.eGui.setAttribute('style', "white-space: normal; line-height: 1.5; font-weight: 700;");
        }
        getGui() { return this.eGui; }
    }
    """)

    return {'url': url_renderer, 'comments': comments_renderer}


def configure_grid_options(df: pd.DataFrame) -> dict:
    """Configure AgGrid options."""
    # Format comments
    if "comments" in df.columns:
        df["comments"] = df["comments"].apply(
            lambda c: "<br>".join(reversed(c)))

    gb = GridOptionsBuilder.from_dataframe(df)

    # Default column configuration
    gb.configure_default_column(
        filter=True,
        sortable=True,
        resizable=True,
        editable=False,
        min_column_width=250
    )

    # Get cell renderers
    renderers = get_cell_renderers()

    # Configure special columns
    hyperlink_columns = {
        "QA_task": {"headerName": "QA Task", "width": 200},
        "Feature ID": {"headerName": "Feature Task Key", "width": 200, "pinned": 'left'},
        "Auto_task": {"headerName": "Auto Task", "width": 200},
        "TMS_task": {"headerName": "TMS Task", "width": 200}
    }

    for col, config in hyperlink_columns.items():
        if col in df.columns:
            gb.configure_column(
                col,
                cellRenderer=renderers['url'],
                filter="agTextColumnFilter",
                **config
            )

    # Configure comments column
    if "comments" in df.columns:
        gb.configure_column(
            "comments",
            wrapText=True,
            autoHeight=True,
            autoWidth=True,
            editable=False,
            cellRenderer=renderers['comments'],
            pinned='left',
            width=200
        )

    # Grid options
    gb.configure_pagination(
        enabled=True, paginationAutoPageSize=False, paginationPageSize=50)
    gb.configure_side_bar()
    gb.configure_selection(selection_mode='single',
                           rowMultiSelectWithClick=True, use_checkbox=True)

    return gb.build()


def get_custom_css() -> Dict[str, Any]:
    """Get custom CSS for AgGrid."""
    return {
        ".ag-root-wrapper": {
            "border": "1px solid #e0e0e0",
            "border-radius": "8px",
            "overflow": "hidden"
        },
        ".ag-header": {
            "background-color": "#f8f9fa",
            "border-bottom": "2px solid #dee2e6"
        },
        ".ag-header-cell-label": {
            "font-size": "13px",
            "font-weight": "600",
            "color": "#212529"
        },
        ".ag-cell": {
            "font-size": "13px",
            "color": "#495057",
            "line-height": "1.5"
        },
        ".ag-row-hover": {
            "background-color": "#f1f3f5 !important"
        },
        ".ag-floating-filter-input": {"font-size": "12px"},
        ".ag-input-field-input": {"font-size": "12px"}
    }


def render_header_section(release: str, df: pd.DataFrame, filtered_count: int) -> bool:
    """Render header section with controls. Returns True if force pull clicked."""
    header_cols = st.columns([2, 2, 2, 2])

    with header_cols[0]:
        st.markdown(
            f'<div class="release-header">📦 Release: {release}</div>', unsafe_allow_html=True)

    with header_cols[1]:
        if filtered_count < len(df):
            st.html(
                f"<div style='font-size: 22px;'>Showing: {filtered_count} / {len(df)} Tickets</div>")
        else:
            st.html(
                f"<div style='font-size: 22px;'>Total Tickets: {len(df)}</div>")

    with header_cols[2]:
        force_pull_btn = st.button(
            "🔄 Force Pull",
            key=f"force_pull_{release}",
            help=f"Fetch latest data for {release}"
        )

    with header_cols[3]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_data = convert_df_to_csv(df)
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"tasks_{release}_{timestamp}.csv",
            mime="text/csv",
            key=f"download_{release}"
        )

    return force_pull_btn


def handle_comment_submission(selected_row: Dict, release: str, new_comment: str) -> bool:
    """Handle comment submission. Returns True if successful."""
    if not new_comment.strip():
        st.warning("⚠️ Please enter a comment before submitting.")
        return False

    try:
        ticket_id = get_ticket_id(
            selected_row['Feature ID'], selected_row['QA_task'])
        ack = comments_addition(
            ticket_id=ticket_id,
            comment=new_comment,
            rocm_version=release
        )
        if ack:
            st.success(
                f"✅ Comment submitted for {selected_row['Feature ID']}!")
            return True
        return False
    except Exception as e:  # pylint: disable=broad-except
        st.error(f"❌ Error submitting comment: {str(e)}")
        return False


def handle_effort_update(selected_row: Dict, release: str, new_effort: str) -> bool:
    """Handle effort update. Returns True if successful."""
    if new_effort == selected_row['Effort']:
        return False

    try:
        ticket_id = get_ticket_id(
            selected_row['Feature ID'], selected_row['QA_task'])
        ack = update_effort(
            ticket_id=ticket_id,
            effort=new_effort,
            rocm_version=release
        )
        return ack
    except Exception as e:  # pylint: disable=broad-except
        st.error(f"❌ Error updating effort: {str(e)}")
        return False


def show_row_details_dialog(selected_row: Dict, release: str):
    """Show dialog with row details and edit options."""
    dialog_key = f"show_dialog_{selected_row['Feature ID']}_{release}"
    if dialog_key not in st.session_state:
        st.session_state[dialog_key] = True

    if dialog_key in st.session_state and not st.session_state[dialog_key] and selected_row["comments"] != "":
        st.session_state[dialog_key] = True

    if st.session_state[dialog_key]:
        @st.dialog(f"{selected_row['Feature ID']} comments")
        def show_details():
            st.write("### Comments")
            comments = selected_row['comments'].split(
                "<br>") if selected_row['comments'] else []
            if comments and comments[0]:
                for comment in comments:
                    st.markdown(f"- {comment}")
            else:
                st.write("No comments found.")

            st.divider()

            effort_key = f"effort_{selected_row['Feature ID']}_{release}"

            if effort_key not in st.session_state:
                st.session_state[effort_key] = selected_row['Effort']

            current_effort = st.selectbox(
                "Size of Ticket",
                EFFORT_SIZES,
                index=EFFORT_SIZES.index(st.session_state[effort_key]),
                key=f"select_{effort_key}",
                help="Select the effort type"
            )

            if current_effort != st.session_state[effort_key]:
                if handle_effort_update(selected_row, release, current_effort):
                    st.session_state[effort_key] = current_effort
                    st.success("✅ Effort updated!")

            st.divider()

            st.write("### Add New Comment")
            new_comment = st.text_area(
                "Enter your comment",
                key=f"comment_input_{selected_row['Feature ID']}_{release}",
                placeholder="Type your comment here..."
            )

            if st.button("Submit Comment", key=f"submit_{selected_row['Feature ID']}_{release}", type="primary"):
                if handle_comment_submission(selected_row, release, new_comment):
                    st.session_state[dialog_key] = False
                    st.rerun()

        show_details()


def render_release_section(release: str):
    """Render a single release section."""
    unique_key = get_rocm_unique_value(release)
    loaded_df = load_data(release=release, unique_key=unique_key)

    # Load data
    force_pull = False
    if not loaded_df.empty:
        # Render analytics first (with unfiltered data for counts)
        render_analytics_section(loaded_df, release)

        # Apply filter to get display data
        filtered_df = apply_filter(loaded_df.copy(), release)

        # Render header
        force_pull = render_header_section(
            release, loaded_df, len(filtered_df))

    if force_pull:
        with st.spinner(f"⏳ Fetching latest data for {release}..."):
            df = load_data_no_cache(release=release, unique_key=unique_key)
            st.success(f"✅ Data refreshed for {release}!")
            clear_filter(release)
            st.rerun()
    else:
        df = filtered_df if not loaded_df.empty else loaded_df

    # Check if empty
    if df.empty:
        st.info(f"ℹ️ No data available for {release}")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # Process DataFrame
    if "_id" in df.columns:
        df["_id"] = df["_id"].astype(str).str.split("|").str[0]
        df = df.rename(columns={"_id": "Feature ID"})

    try:
        # Configure and display grid
        grid_options = configure_grid_options(df)
        grid_response = AgGrid(
            df,
            gridOptions=grid_options,
            enable_enterprise_modules='enterprise+AgCharts',
            fit_columns_on_grid_load=True,
            height=650,
            update_mode=GridUpdateMode.NO_UPDATE,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            theme="alpine",
            custom_css=get_custom_css(),
            allow_unsafe_jscode=True,
            key=f"grid_{release}"
        )

        # Handle selected rows
        if grid_response['selected_rows'] is not None and len(grid_response['selected_rows']) > 0:
            selected_row = grid_response['selected_rows'].iloc[0].to_dict()
            show_row_details_dialog(selected_row, release)

    except Exception as e:  # pylint: disable=broad-except
        st.error(f"❌ Error rendering grid: {str(e)}")
        st.info(
            "💡 The data was loaded successfully but couldn't be displayed. "
            "Check the data format and try again."
        )

    st.markdown('</div>', unsafe_allow_html=True)


def main():
    """Main application entry point."""
    rocm_versions = sorted(get_rocm_versions(), reverse=True)

    # Release selection
    selected_releases = st.multiselect(
        "Select Release Version(s)",
        rocm_versions,
        help="Select one or more release versions to view data"
    )

    if not selected_releases:
        st.info("ℹ️ Please select at least one release version to view data.")
        return

    st.divider()

    # Display each release
    for release in selected_releases:
        render_release_section(release)


if __name__ == "__main__":
    main()
