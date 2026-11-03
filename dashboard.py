# BC Wildfire Explorer
# A one screen Streamlit dashboard built on public BC wildfire data.


# 1. Imports and page setup

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import pydeck as pdk
import requests
import streamlit as st

st.set_page_config(page_title="BC Wildfire Explorer", layout="wide", initial_sidebar_state="collapsed")

# Web services for the fire data and the province outline
fire_url = "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_land_and_natural_resource/MapServer/6/query"
boundary_url = "https://geo.statcan.gc.ca/geo_wa/rest/services/2021/Cartographic_boundary_files/MapServer/0/query"

# Everything downloaded is saved here, so each request only happens once
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)

# Base map choices, the first one is the default (satellite is added as an extra layer further down)
basemap_styles = {"Satellite": "light", "Light": "light", "Streets": "road", "Dark": "dark"}

# Colours for the fire causes
cause_colors = {"Lightning": "#f8766d", "Person": "#00ba38", "Unknown": "#619cff"}


# 2. Data

# Number of fires and hectares burned for every year and cause
fires_file = data_dir / "fires_by_cause.csv"
if fires_file.exists():
    fires = pd.read_csv(fires_file)
else:
    query = {
        "where": "FIRE_YEAR >= 2000 AND FIRE_YEAR <= 2025",
        "groupByFieldsForStatistics": "FIRE_YEAR,FIRE_CAUSE",
        "outStatistics": json.dumps([
            {"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "FIRE_COUNT"},
            {"statisticType": "sum", "onStatisticField": "FIRE_SIZE_HECTARES", "outStatisticFieldName": "AREA_BURNED"}
        ]),
        "returnGeometry": "false",
        "f": "json"
    }
    response = requests.get(fire_url, params=query, timeout=60)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        st.error(result["error"]["message"])
        st.stop()
    fires = pd.DataFrame([row["attributes"] for row in result["features"]])
    fires.columns = fires.columns.str.lower()
    # Fires with no recorded cause are grouped as Unknown
    fires["fire_cause"] = fires["fire_cause"].fillna("Unknown")
    fires = fires.groupby(["fire_year", "fire_cause"], as_index=False).sum()
    fires.to_csv(fires_file, index=False)

# Totals for each year, used by the summary cards and the yearly chart
annual = fires.groupby("fire_year", as_index=False)[["fire_count", "area_burned"]].sum()
years = sorted(annual["fire_year"].astype(int).unique())

# The province outline, saved after the first download
boundary_file = data_dir / "bc_boundary_simple.json"
boundary = None
if boundary_file.exists():
    boundary = json.loads(boundary_file.read_text(encoding="utf-8"))
else:
    query = {
        "where": "PRUID = '59'",
        "outFields": "PRNAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": 0.03,
        "geometryPrecision": 3,
        "f": "geojson"
    }
    response = requests.get(boundary_url, params=query, timeout=60)
    if response.ok and response.json().get("type") == "FeatureCollection":
        boundary = response.json()
        # Keep only the mainland and the largest islands so the outline stays clean
        for feature in boundary["features"]:
            geometry = feature["geometry"]
            if geometry["type"] == "MultiPolygon":
                polygons = geometry["coordinates"]
            else:
                polygons = [geometry["coordinates"]]
            large_polygons = []
            for polygon in polygons:
                ring = polygon[0]
                width = max(point[0] for point in ring) - min(point[0] for point in ring)
                height = max(point[1] for point in ring) - min(point[1] for point in ring)
                if max(width, height) > 0.8:
                    large_polygons.append([ring])
            feature["geometry"] = {"type": "MultiPolygon", "coordinates": large_polygons}
        boundary_file.write_text(json.dumps(boundary), encoding="utf-8")
    else:
        st.warning("Could not load the BC boundary.")


# 3. Page style

# Hides the Streamlit header, colours the three panels and sizes the map to the window
st.markdown("""
<style>
header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none !important;}
.stApp {background: #e4e8ec;}
.block-container {padding: 0.5rem 0.75rem 0 0.75rem !important; max-width: 100% !important;}
[data-testid="stVerticalBlock"] {gap: 0.4rem;}

/* The empty marker div lets us style only the three main columns */
.panel {display: none;}
[data-testid="stColumn"]:has(.panel), [data-testid="column"]:has(.panel) {
    background: #93aac1;
    border: 1px solid #6f8aa5;
    border-radius: 4px;
    padding: 0.75rem !important;
    min-height: calc(100vh - 5.1rem);
}

/* Dark text so everything stays readable on the coloured panels */
[data-testid="stColumn"]:has(.panel) p, [data-testid="column"]:has(.panel) p,
[data-testid="stColumn"]:has(.panel) label, [data-testid="column"]:has(.panel) label,
[data-testid="stColumn"]:has(.panel) h3, [data-testid="column"]:has(.panel) h3,
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"],
[data-testid="stTickBarMin"], [data-testid="stTickBarMax"] {color: #14202b !important;}

.header {background: #2f3a45; color: white; padding: 0.5rem 1rem; border-radius: 4px; font-size: 1.2rem; font-weight: 600;}
.header span {font-weight: 400; font-size: 0.8rem; color: #c5ccd3; margin-left: 1rem;}
h3 {font-size: 1rem !important; margin: 0 !important; padding: 0 !important;}

/* The map fills the window height */
[data-testid="stDeckGlJsonChart"], [data-testid="stDeckGlJsonChart"] > div {
    height: calc(100vh - 7rem) !important;
}

/* White cards for the numbers and charts */
[data-testid="stMetric"] {background: white; border: 1px solid #b4c4d4; border-radius: 4px; padding: 0.4rem 0.7rem;}
[data-testid="stMetricValue"] {font-size: 1.4rem;}
[data-testid="stPlotlyChart"] {background: white; border-radius: 4px;}
.swatch {display: inline-block; width: 22px; height: 14px; margin-right: 8px; vertical-align: middle;}
</style>
""", unsafe_allow_html=True)


# 4. Header and layout

st.markdown(
    f'<div class="header">BC Wildfire Explorer<span>Historical wildfire perimeters, {min(years)}–{max(years)}</span></div>',
    unsafe_allow_html=True
)

left, middle, right = st.columns([1.1, 4.6, 1.9], gap="small")


# 5. Left panel: filters and legend

with left:
    st.markdown('<div class="panel"></div>', unsafe_allow_html=True)
    st.subheader("Filters")

    start_year, end_year = st.slider(
        "Year range (charts)", min(years), max(years), (min(years), max(years))
    )
    map_year = st.selectbox(
        "Selected year (map and summary)", [year for year in reversed(years) if start_year <= year <= end_year]
    )
    basemap = st.selectbox("Base map", list(basemap_styles))
    show_perimeters = st.checkbox("Show perimeters", value=True)
    show_boundary = st.checkbox("Show BC boundary", value=True)
    st.divider()

    # The boundary line turns white on the dark and satellite maps so it stays visible
    if basemap in ["Dark", "Satellite"]:
        boundary_color, swatch_fill = [255, 255, 255], "#6b7785"
    else:
        boundary_color, swatch_fill = [60, 60, 60], "transparent"
    boundary_css = f"rgb({boundary_color[0]},{boundary_color[1]},{boundary_color[2]})"

    st.markdown("**Legend**")
    st.markdown(
        '<span class="swatch" style="background: rgba(220,90,45,0.55); border: 2px solid #a03723;"></span>Wildfire perimeter',
        unsafe_allow_html=True
    )
    st.markdown(
        f'<span class="swatch" style="background: {swatch_fill}; border: 2px solid {boundary_css};"></span>BC boundary',
        unsafe_allow_html=True
    )


# 6. Numbers for the selected year and year range

filtered = annual[annual["fire_year"].between(start_year, end_year)]
year_row = annual[annual["fire_year"] == map_year].iloc[0]

# Main cause of the selected year, measured by area burned
year_causes = fires[fires["fire_year"] == map_year]
main_cause = year_causes.loc[year_causes["area_burned"].idxmax()]
main_cause_share = main_cause["area_burned"] / year_causes["area_burned"].sum() * 100


# 7. Middle panel: the map

with middle:
    st.markdown('<div class="panel"></div>', unsafe_allow_html=True)

    # Every fire perimeter of the selected year, largest first, saved after the first download
    perimeter_file = data_dir / f"perimeters_all_{map_year}.json"
    if perimeter_file.exists():
        perimeters = json.loads(perimeter_file.read_text(encoding="utf-8"))
    else:
        query = {
            "where": f"FIRE_YEAR = {map_year}",
            "outFields": "FIRE_NUMBER,FIRE_YEAR,FIRE_SIZE_HECTARES",
            "returnGeometry": "true",
            "outSR": "4326",
            "orderByFields": "FIRE_SIZE_HECTARES DESC",
            "resultRecordCount": 2000,
            "maxAllowableOffset": 0.02,
            "geometryPrecision": 3,
            "f": "geojson"
        }
        with st.spinner("Loading fire perimeters..."):
            response = requests.get(fire_url, params=query, timeout=90)
            response.raise_for_status()
            perimeters = response.json()
        if perimeters.get("type") != "FeatureCollection":
            st.error("Could not load the wildfire map.")
            st.stop()
        perimeter_file.write_text(json.dumps(perimeters), encoding="utf-8")

    layers = []

    # Satellite imagery is drawn as a flat layer under the fires
    if basemap == "Satellite":
        layers.append(pdk.Layer(
            "TerrainLayer",
            texture="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
            elevation_decoder={"rScaler": 0, "gScaler": 0, "bScaler": 0, "offset": 0},
            max_zoom=15
        ))

    if show_perimeters:
        layers.append(pdk.Layer(
            "GeoJsonLayer", perimeters,
            filled=True,
            get_fill_color=[220, 90, 45, 140],
            get_line_color=[160, 55, 35],
            pickable=True,
            parameters={"depthTest": False}
        ))

    if show_boundary and boundary is not None:
        layers.append(pdk.Layer(
            "GeoJsonLayer", boundary,
            stroked=True,
            filled=False,
            get_line_color=boundary_color,
            line_width_min_pixels=1,
            parameters={"depthTest": False}
        ))

    st.pydeck_chart(pdk.Deck(
        layers=layers,
        map_style=basemap_styles[basemap],
        initial_view_state=pdk.ViewState(latitude=54.5, longitude=-126.5, zoom=4.7),
        tooltip={"text": "Fire: {FIRE_NUMBER}\nSize: {FIRE_SIZE_HECTARES} ha"}
    ))


# 8. Left panel again: how much of the year the map shows

shown = len(perimeters["features"])
shown_area = sum((feature["properties"]["FIRE_SIZE_HECTARES"] or 0) for feature in perimeters["features"])

with left:
    st.divider()
    if shown >= year_row["fire_count"]:
        st.caption(f"The map shows all {shown} fires recorded in {map_year}.")
    else:
        share = shown_area / year_row["area_burned"] * 100
        st.caption(
            f"The map shows the {shown} largest of {int(year_row['fire_count']):,} fires in {map_year}. "
            f"Together they make up {share:.0f}% of the area burned that year."
        )
    if basemap == "Satellite":
        st.caption("Imagery: Esri, Maxar, Earthstar Geographics.")


# 9. Right panel: summary cards and charts

with right:

    top_left, top_right = st.columns(2)
    bottom_left, bottom_right = st.columns(2)

    top_left.metric("Fires recorded", f"{int(year_row['fire_count']):,}")

    top_right.metric(
        "Area burned (ha)", f"{year_row['area_burned']:,.0f}",
        help="Fire records can overlap, so some land may be counted twice."
    )

    if perimeters["features"]:
        largest = perimeters["features"][0]["properties"]
        bottom_left.metric(
            "Largest fire (ha)", f"{largest['FIRE_SIZE_HECTARES']:,.0f}",
            help=f"Fire number {largest['FIRE_NUMBER']}"
        )

    bottom_right.metric(
        "Main cause", main_cause["fire_cause"],
        delta=f"{main_cause_share:.0f}% of area", delta_color="off", delta_arrow="off"
    )

    # Shared look for both charts
    chart_layout = dict(
        height=300, margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="white", plot_bgcolor="white"
    )

    tab_year, tab_cause = st.tabs(["Area burned by year", "By cause"])

    with tab_year:
        chart = px.bar(
            filtered, x="fire_year", y="area_burned",
            labels={"fire_year": "Year", "area_burned": "Area (ha)"}
        )
        # The selected year is orange, all other years are grey blue
        bar_colors = ["#d9541e" if year == map_year else "#8fa3b8" for year in filtered["fire_year"]]
        chart.update_traces(marker_color=bar_colors)
        chart.update_layout(**chart_layout)
        st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
        st.caption(f"The orange bar is {map_year}.")

    with tab_cause:
        by_cause = fires[fires["fire_year"].between(start_year, end_year)]
        chart = px.bar(
            by_cause, x="fire_year", y="area_burned", color="fire_cause",
            color_discrete_map=cause_colors,
            category_orders={"fire_cause": ["Person", "Unknown", "Lightning"]},
            labels={"fire_year": "Year", "area_burned": "Area (ha)", "fire_cause": "Cause"}
        )
        chart.update_layout(**chart_layout, legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", title_text=""))
        st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
        st.caption("Area burned each year, split by the cause of the fire.")
