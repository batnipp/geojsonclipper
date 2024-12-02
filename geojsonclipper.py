import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import json
import geopandas as gpd
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
import pandas as pd
import numpy as np
from math import ceil

# Enable caching for better performance
@st.cache_data
def load_geojson(uploaded_file):
    data = json.load(uploaded_file)
    return gpd.GeoDataFrame.from_features(data['features'])

@st.cache_data
def load_csv(uploaded_file, lat_col, lon_col):
    df = pd.read_csv(uploaded_file)
    return gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
        crs="EPSG:4326"
    )

st.set_page_config(layout="wide")
st.title('GeoJSON Shrinker Tool')

# Step 1: File Upload
st.write("### Step 1: Upload your file")
uploaded_file = st.file_uploader("Choose a GeoJSON or CSV file (Limit 1GB per file)", type=['geojson', 'csv'])

if uploaded_file is not None:
    # Detect file type
    file_type = uploaded_file.name.split('.')[-1].lower()
    
    try:
        with st.spinner('Loading data...'):
            if file_type == 'geojson':
                gdf = load_geojson(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)
                st.write("### Select Coordinate Columns")
                lat_col = st.selectbox("Select Latitude Column", df.columns.tolist())
                lon_col = st.selectbox("Select Longitude Column", df.columns.tolist())
                gdf = load_csv(uploaded_file, lat_col, lon_col)
        
        # Display initial count
        st.write(f"Total number of features: {len(gdf)}")
        
        # Add column filtering
        st.write("### Filter by Properties (Optional)")
        columns = [col for col in gdf.columns if col != 'geometry']
        if columns:
            selected_column = st.selectbox("Select property to filter by:", columns)
            unique_values = gdf[selected_column].unique()
            selected_values = st.multiselect(
                f"Select values to keep from {selected_column}:",
                unique_values
            )
            if selected_values:
                gdf = gdf[gdf[selected_column].isin(selected_values)]
                st.write(f"Features after filtering: {len(gdf)}")

      # Replace the entire "Merge Overlapping Features" section with this:

        # Merge Overlapping Features
        st.write("### Merge Overlapping Features (Optional)")
        merge_features = st.checkbox("Merge overlapping features")
        if merge_features:
            col1, col2 = st.columns(2)
            with col1:
                buffer_distance = st.number_input(
                    "Buffer distance in meters",
                    min_value=1, value=25, max_value=100,
                    help="Initial buffer to create overlap between nearby features"
                )
            with col2:
                overlap_threshold = st.slider(
                    "Minimum overlap percentage to merge",
                    min_value=0, max_value=100, value=50,
                    help="Features will merge only if they overlap by at least this percentage"
                )

            try:
                # 1. Original Features Map
                st.write("### Step 1: Original Features")
                m1 = folium.Map(
                    location=[gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()],
                    zoom_start=14
                )
                
                for _, row in gdf.iterrows():
                    folium.Circle(
                        location=[row.geometry.centroid.y, row.geometry.centroid.x],
                        radius=2,
                        color='red',
                        fill=True
                    ).add_to(m1)
                
                st.write("🔴 Original features")
                st_folium(m1, width=725, height=400)

                # 2. Buffered Features Map
                st.write(f"### Step 2: Features with {buffer_distance}m Buffer")
                m2 = folium.Map(
                    location=[gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()],
                    zoom_start=14
                )
                
                buffered_gdf = gdf.copy()
                buffered_gdf['geometry'] = buffered_gdf.geometry.buffer(buffer_distance)
                
                for _, row in buffered_gdf.iterrows():
                    folium.Circle(
                        location=[row.geometry.centroid.y, row.geometry.centroid.x],
                        radius=buffer_distance,
                        color='orange',
                        fill=True,
                        fill_opacity=0.3
                    ).add_to(m2)
                
                st.write("🟡 Features with buffer applied")
                st_folium(m2, width=725, height=400)

                # 3. Merge overlapping features
                st.write(f"### Step 3: Merged Features (>{overlap_threshold}% overlap)")
                
                # Simple merging algorithm
                merged_features = []
                processed = set()
                
                for i in range(len(buffered_gdf)):
                    if i in processed:
                        continue
                        
                    current_group = [i]
                    current_geom = buffered_gdf.iloc[i].geometry
                    
                    for j in range(i + 1, len(buffered_gdf)):
                        if j in processed:
                            continue
                            
                        test_geom = buffered_gdf.iloc[j].geometry
                        if current_geom.intersects(test_geom):
                            intersection_area = current_geom.intersection(test_geom).area
                            min_area = min(current_geom.area, test_geom.area)
                            overlap_percentage = (intersection_area / min_area) * 100
                            
                            if overlap_percentage > overlap_threshold:
                                current_group.append(j)
                                current_geom = unary_union([current_geom, test_geom])
                                processed.add(j)
                    
                    if current_group:
                        merged_features.append({
                            'geometry': current_geom,
                            'original_count': len(current_group),
                            'center': current_geom.centroid
                        })
                    processed.add(i)
                
                # Create merged GeoDataFrame
                merged = gpd.GeoDataFrame(merged_features, crs=gdf.crs)
                
                # Display merged features
                m3 = folium.Map(
                    location=[gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()],
                    zoom_start=14
                )
                
                # Show original features as small red dots
                for _, row in gdf.iterrows():
                    folium.Circle(
                        location=[row.geometry.centroid.y, row.geometry.centroid.x],
                        radius=2,
                        color='red',
                        fill=True
                    ).add_to(m3)
                
                # Show merged features as blue circles
                for _, row in merged.iterrows():
                    radius = max(buffer_distance, 25)  # Use a minimum radius for visibility
                    folium.Circle(
                        location=[row.center.y, row.center.x],
                        radius=radius,
                        color='blue',
                        fill=True,
                        fill_opacity=0.3,
                        popup=f"Contains {row.original_count} original features"
                    ).add_to(m3)
                
                st.write("🔴 Original features")
                st.write("🔵 Merged features")
                st_folium(m3, width=725, height=400)
                
                # Show statistics
                st.write("### Merge Statistics")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Original Features", len(gdf))
                with col2:
                    st.metric("Merged Features", len(merged))
                with col3:
                    reduction = ((len(gdf) - len(merged)) / len(gdf) * 100)
                    st.metric("Reduction", f"{reduction:.1f}%")
                
                # Option to use merged features
                if st.checkbox("✅ Use merged features for lasso selection"):
                    gdf = merged
                    st.success("Now you can use the lasso tool below to select which merged features to keep.")

            except Exception as e:
                st.error(f"Error during merging: {str(e)}")
                st.error("Please try adjusting the buffer distance or overlap threshold.")

        # Map settings
        st.write("### Step 2: Draw a polygon around the features you want to keep")
        basemap = st.selectbox(
            'Select map style:',
            ('OpenStreetMap', 'Satellite'),
            index=0
        )
        
        tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}' if basemap == 'Satellite' else 'OpenStreetMap'
        attr = 'Esri' if basemap == 'Satellite' else None
        
        # Create base map
        m = folium.Map(
            location=[gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()],
            zoom_start=14,
            tiles=tiles,
            attr=attr
        )
        
        # Add features to map
        for idx, row in gdf.iterrows():
            radius = 2  # Default radius
            if merge_features and 'original_count' in gdf.columns:
                radius = max(25, row.geometry.bounds[2] - row.geometry.bounds[0])
            
            folium.Circle(
                location=[row.geometry.centroid.y, row.geometry.centroid.x],
                radius=radius,
                color='red',
                fill=True,
                popup=f"Features merged: {row.get('original_count', 1)}" if 'original_count' in gdf.columns else None
            ).add_to(m)
        
        # Add draw control
        draw = Draw(
            draw_options={
                'polyline': False,
                'rectangle': False,
                'circle': False,
                'circlemarker': False,
                'marker': False,
                'polygon': True
            },
            export=True
        )
        m.add_child(draw)
        
        # Display the map
        output = st_folium(m, width=725, height=600)
        
        # Process selection if a polygon is drawn
        if output and output.get('last_active_drawing'):
            selection = output['last_active_drawing']
            if selection['geometry']['type'] == 'Polygon':
                select_poly = Polygon(selection['geometry']['coordinates'][0])
                selected_signals = gdf[gdf.apply(lambda row: select_poly.contains(row.geometry.centroid), axis=1)]
                
                st.write(f"### Selected {len(selected_signals)} out of {len(gdf)} features")
                
                if len(selected_signals) > 0:
                    st.write("### Download Options")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # GeoJSON Download
                        geojson_data = json.dumps({
                            "type": "FeatureCollection",
                            "features": json.loads(selected_signals.to_json())['features']
                        })
                        st.download_button(
                            label="📥 Download as GeoJSON",
                            data=geojson_data,
                            file_name="selected_features.geojson",
                            mime="application/json",
                            help="Download the selected features in GeoJSON format"
                        )
                    
                    with col2:
                        # CSV Download
                        output_df = pd.DataFrame(selected_signals.drop(columns=['geometry']))
                        output_df['latitude'] = selected_signals.geometry.y
                        output_df['longitude'] = selected_signals.geometry.x
                        csv_data = output_df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download as CSV",
                            data=csv_data,
                            file_name="selected_features.csv",
                            mime="text/csv",
                            help="Download the selected features in CSV format with latitude and longitude columns"
                        )

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        st.error("Please check your file format and try again.")