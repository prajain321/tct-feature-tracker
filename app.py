import json
import streamlit as st 
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode
from packages.ticketfetchers.ticket_fetcher_optimized import TicketFetch
from common import get_rocm_unique_value, get_rocm_versions
from packages.balancer import balance, force_refetch_and_update, comments_addition
from datetime import datetime

JIRA_BASE_URL = "https://ontrack-internal.amd.com/browse/"

# Page configuration
st.set_page_config(
    page_title="Task Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main > div {
        padding-top: 2rem;
    }
    h1 {
        color: #1f77b4;
        font-weight: 600;
        margin-bottom: 2rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
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
    /* Remove white spacing/patches */
    .block-container {
        padding-top: 1rem;
    }
    div[data-testid="stVerticalBlock"] > div:has(> div.element-container) {
        gap: 0rem;
    }
    </style>
""", unsafe_allow_html=True)


def load_data(release: str, unique_key: int) -> pd.DataFrame:
    """
    Load data from JSON file with error handling.
    
    Args:
        release: ROCm release version
        unique_key: Unique key for the release
        
    Returns:
        DataFrame containing the loaded data
    """
    try:
        with st.spinner(f"⏳ Loading data for {release}..."):
            data = balance(rocm_version=release, unique_key=str(unique_key))
            return pd.DataFrame(data)
    except Exception as e:
        st.warning(f"⚠️ No Tickets Found for {release}")
        return pd.DataFrame()


def load_data_no_cache(release: str, unique_key: int) -> pd.DataFrame:
    """
    Load data without caching - always fetches fresh data from server.
    
    Args:
        release: ROCm release version
        unique_key: Unique key for the release
        
    Returns:
        DataFrame containing the loaded data
    """
    try:
        tf = TicketFetch(max_workers=6, verbose=True, rocm_version=release, unique_key=str(unique_key))
        force_refetch_and_update(rocm_version=release, unique_key=str(unique_key))
        return tf.fetch_tickets()
    except Exception as e:
        st.warning(f"⚠️ No Tickets Found for {release}")
        return pd.DataFrame()


def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """
    Convert DataFrame to CSV bytes for download.
    
    Args:
        df: DataFrame to convert
        
    Returns:
        CSV data as bytes
    """
    return df.to_csv(index=False).encode('utf-8')


def configure_grid_options(df: pd.DataFrame) -> dict:
    """
    Configure AgGrid options for professional appearance.
    
    Args:
        df: DataFrame to configure
        
    Returns:
        Grid options dictionary
    """
    def format_comments(comments):
        return "<br>".join(reversed(comments))
    if "comments" in df.columns:
        df["comments"] =  df["comments"].apply(format_comments)
    
    gb = GridOptionsBuilder.from_dataframe(df)
    
    # Enable filtering and sorting
    gb.configure_default_column(
        filter=True,
        sortable=True,
        resizable=True,
        editable=False
    )
    
    # JavaScript code for hyperlink rendering
    cell_renderer = JsCode("""
    class UrlCellRenderer {
        init(params) {
            this.eGui = document.createElement('a');
            this.eGui.innerText = params.value;
            this.eGui.setAttribute('href', 'https://ontrack-internal.amd.com/browse/' + params.value);
            this.eGui.setAttribute('style', "text-decoration:none");
            this.eGui.setAttribute('target', "_blank");
        }
        getGui() {
            return this.eGui;
        }
    }
    """)
    
    # Custom cell renderer for comments with HTML support
    comments_cell_renderer = JsCode("""
    class CommentsCellRenderer {
        init(params) {
            this.eGui = document.createElement('div');
            this.eGui.innerHTML = params.value || '';
            this.eGui.setAttribute('style', "white-space: normal; line-height: 1.5;");
        }
        getGui() {
            return this.eGui;
        }
    }
    """)
    
    # Special configuration for hyperlink columns
    if "QA_task" in df.columns:
        gb.configure_column(
            "QA_task",
            headerName="QA_task",
            cellRenderer=cell_renderer,
            filter="agTextColumnFilter",
            width=200
        )
    
    if "Feature ID" in df.columns:
        gb.configure_column(
            "Feature ID",
            headerName="Feature Task Key",
            cellRenderer=cell_renderer,
            filter="agTextColumnFilter",
            width=200,
            pinned='left'
        )
    
        if "comments" in df.columns:
            gb.configure_column(
                "comments", 
                wrapText=True, 
                autoHeight=True, 
                editable=False,
                cellRenderer=comments_cell_renderer,
                pinned='left'
            )
    
    # Enable pagination for better performance with large datasets
    gb.configure_pagination(
        enabled=True,
        paginationAutoPageSize=False,
        paginationPageSize=50
    )
    
    # Enable sidebar for advanced filtering
    gb.configure_side_bar()
    
    # Enable grid options
    gb.configure_selection(selection_mode='single', rowMultiSelectWithClick=True , use_checkbox=True)
    
    return gb.build()


def render_release_section(release: str):
    """
    Render a single release section with its data and controls.
    
    Args:
        release: Release version to display
    """
    unique_key = get_rocm_unique_value(release)
    loaded_df = load_data(release=release, unique_key=unique_key)
    
    # Header with Force Pull button
    header_col1, header_col2, header_col3 , header_col4 = st.columns([2, 2,2,2])
    with header_col1:
        st.markdown(f'<div class="release-header">📦 Release: {release}</div>', unsafe_allow_html=True)
    with header_col2:
        st.html(f"<div style='font-size: 22px;'>Total Tickets: {len(loaded_df)}</div>")
    with header_col3:
        force_pull_btn = st.button(
            "🔄 Force Pull", 
            key=f"force_pull_{release}",
            help=f"Fetch latest data for {release}"
        )
    with header_col4:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_data = convert_df_to_csv(loaded_df)
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"tasks_{release}_{timestamp}.csv",
            mime="text/csv",
            key=f"download_{release}"
        )
    
    # Load data
    if force_pull_btn:
        with st.spinner(f"⏳ Fetching latest data for {release}..."):
            df = load_data_no_cache(release=release, unique_key=unique_key)
            st.success(f"✅ Data refreshed for {release}!")
    else:
        df = loaded_df
    
    # Check if DataFrame is empty
    if df.empty:
        st.info(f"ℹ️ No data available for {release}")
        st.markdown('</div>', unsafe_allow_html=True)
        return
    
    # Process DataFrame
    if "_id" in df.columns:
        df["_id"] = df["_id"].astype(str).str.split("|").str[0]
        df = df.rename(columns={"_id": "Feature ID"})
    
    try:
        # Configure grid
        grid_options = configure_grid_options(df)
        
        # Custom CSS for AgGrid
        custom_css = {
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
            ".ag-floating-filter-input": {
                "font-size": "12px"
            },
            ".ag-input-field-input": {
                "font-size": "12px"
            }
        }
        
        # Display the grid
        grid_response = AgGrid(
            df,
            gridOptions=grid_options,
            enable_enterprise_modules='enterprise+AgCharts',
            fit_columns_on_grid_load=True,
            height=650,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            theme="alpine",
            custom_css=custom_css,
            allow_unsafe_jscode=True,
            key=f"grid_{release}"
        )
        
        # Display selected rows information
        if grid_response['selected_rows'] is not None and len(grid_response['selected_rows']) > 0:
            # Convert DataFrame to dict for the first row
            selected_row = grid_response['selected_rows'].iloc[0].to_dict()
            
            # Check if we should show dialog (not just after submission)
            dialog_key = f"show_dialog_{selected_row['Feature ID']}_{release}"
            if dialog_key not in st.session_state:
                st.session_state[dialog_key] = True
            
            if st.session_state[dialog_key]:
                @st.dialog(f"{selected_row['Feature ID']} comments")
                def show_details():
                    # Display existing comments
                    comments = selected_row['comments'].split("<br>") if selected_row['comments'] else []
                    st.write("### Comments")
                    if len(comments) > 0 and comments[0]:
                        for comment in comments:
                            st.markdown(f"- {comment}")
                    else:
                        st.write("No comments found.")
                    
                    st.divider()
                    
                    # Add new comment section
                    st.write("### Add New Comment")
                    new_comment = st.text_area(
                        "Enter your comment",
                        key=f"comment_input_{selected_row['Feature ID']}_{release}",
                        placeholder="Type your comment here...",
                    )
                    
                    # Submit button
                    if st.button("Submit Comment", key=f"submit_{selected_row['Feature ID']}_{release}", type="primary"):
                        if new_comment.strip():
                            try:
                                qa_task_key = selected_row['QA_task']
                                if "SWDEV" in qa_task_key:
                                    qa_task_key = "|"+qa_task_key
                                else:
                                    qa_task_key = ""
                                ack = comments_addition(
                                    ticket_id=f"{selected_row['Feature ID']}{qa_task_key}",
                                    comment=new_comment,
                                    rocm_version=release
                                )
                                if ack:
                                    st.success(f"✅ Comment submitted for {selected_row['Feature ID']}!")
                                    # Hide dialog and trigger rerun
                                    st.session_state[dialog_key] = False
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error submitting comment: {str(e)}")
                        else:
                            st.warning("⚠️ Please enter a comment before submitting.")
                show_details()
            else:
                # Reset the dialog state for next selection
                st.session_state[dialog_key] = True
            

    except Exception as e:
        st.error(f"❌ Error rendering grid: {str(e)}")
        st.info("💡 The data was loaded successfully but couldn't be displayed. Check the data format and try again.")
    
    st.markdown('</div>', unsafe_allow_html=True)


rocm_versions = sorted(get_rocm_versions(), reverse=True)


# Main application
def main():    
    # Info section
    selected_releases = st.multiselect(
        "Select Release Version(s)",
        rocm_versions,
        default=[rocm_versions[0]] if rocm_versions else [],
        help="Select one or more release versions to view"
    )
    
    # Check if any releases are selected
    if not selected_releases:
        st.info("ℹ️ Please select at least one release version to view data.")
        return

    st.divider()
    
    # Display data for each selected release
    for release in selected_releases:
        render_release_section(release)

if __name__ == "__main__":
    main()