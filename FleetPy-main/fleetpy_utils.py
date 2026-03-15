import os
import json
import geopandas as gpd
from shapely.geometry import Point, LineString
from pyproj import Transformer

import pyproj
import osmnx as ox
import networkx as nx

class FleetPyNetworkHelper:
    def __init__(self, fleetpy_main_dir, network_name="example_network"):
        self.fleetpy_main_dir = fleetpy_main_dir
        self.network_name = network_name
        self.INPUT_LONLAT_CRS = "EPSG:4326"  # WGS84 - Latitude/Longitude
        self.PROJECTED_CRS = "EPSG:32632"   # UTM Zone 32N (suitable for Germany, adjust as needed)

        self.network_dir = os.path.join(self.fleetpy_main_dir, "data", "networks", self.network_name)
        # OSMnx graph file path
        self.osmnx_graph_path = os.path.join(self.network_dir, "base", f"{self.network_name}.graphml")

        # Load the OSMnx graph
        if os.path.exists(self.osmnx_graph_path):
            self.G = ox.load_graphml(self.osmnx_graph_path)
            print(f"OSMnx graph loaded from {self.osmnx_graph_path}")
        else:
            # Construct OSMnx graph from existing GeoJSON files if graphml doesn't exist
            print(f"Warning: OSMnx graph not found at {self.osmnx_graph_path}. Attempting to construct from GeoJSON files.")
            nodes_geojson_path = os.path.join(self.network_dir, "base", "nodes_all_infos.geojson")
            edges_geojson_path = os.path.join(self.network_dir, "base", "edges_all_infos.geojson")

            if not os.path.exists(nodes_geojson_path) or not os.path.exists(edges_geojson_path):
                raise FileNotFoundError(f"Required GeoJSON files not found: {nodes_geojson_path}, {edges_geojson_path}")

            # Load nodes and edges GeoDataFrames
            gdf_nodes = gpd.read_file(nodes_geojson_path)
            gdf_edges = gpd.read_file(edges_geojson_path)

            # Convert coordinates to WGS84 (lon/lat) if not already
            if gdf_nodes.crs and str(gdf_nodes.crs) != self.INPUT_LONLAT_CRS:
                gdf_nodes = gdf_nodes.to_crs(self.INPUT_LONLAT_CRS)
            if gdf_edges.crs and str(gdf_edges.crs) != self.INPUT_LONLAT_CRS:
                gdf_edges = gdf_edges.to_crs(self.INPUT_LONLAT_CRS)
            
            # Ensure nodes have 'x' and 'y' columns
            gdf_nodes['x'] = gdf_nodes.geometry.x
            gdf_nodes['y'] = gdf_nodes.geometry.y

            # Rename node_index to osmid for compatibility
            # Assuming node_index is unique and can serve as osmid
            gdf_nodes = gdf_nodes.set_index('node_index')
            gdf_nodes.index.name = 'osmid'

            # Prepare edges for graph_from_gdfs
            # Need 'u', 'v', 'key' columns. Assuming key=0 for simplicity (not a multi-graph initially)
            gdf_edges['u'] = gdf_edges['from_node']
            gdf_edges['v'] = gdf_edges['to_node']
            gdf_edges['key'] = 0 # Default key for non-multi-graphs or if keys are not in data

            # Set index for edges. osmnx expects (u, v, key) as MultiIndex
            gdf_edges = gdf_edges.set_index(['u', 'v', 'key'])

            # Create the OSMnx graph
            self.G = ox.graph_from_gdfs(gdf_nodes, gdf_edges)
            print("OSMnx graph constructed from GeoJSON files.")
            
            # Manually add speed and travel time to edges as GeoJSON might not have 'highway' tag
            # 进一步降低速度，让车辆在可视化中移动得更慢、更容易观察
            default_speed_kmh = 0.6  # ~0.6 km/h, very slow for clear visualization
            default_speed_mps = default_speed_kmh * 1000 / 3600  # meters per second
            for u, v, k, data in self.G.edges(keys=True, data=True):
                if 'length' in data:
                    data['speed_kmh'] = default_speed_kmh
                    data['travel_time'] = data['length'] / default_speed_mps  # time in seconds
                else:
                    data['speed_kmh'] = default_speed_kmh # Assign default even if no length
                    data['travel_time'] = 1 # Assign a default travel time (e.g., 1 second) if no length

            print("Manually added edge speeds and travel times to the graph.")
            
            # Apply a preference for "small road" types to encourage their use in pathfinding
            for u, v, k, data in self.G.edges(keys=True, data=True):
                road_type = data.get('road_type')
                if road_type in ['residential', 'service', 'track', 'path', 'living_street']:
                    if 'travel_time' in data:
                        data['travel_time'] *= 0.9 # Make these roads slightly more attractive

            # Check graph connectivity and simplify to largest connected component
            # Use networkx functions for connectivity as self.G is a networkx graph
            undirected_G = self.G.to_undirected()
            if not nx.is_connected(undirected_G):
                print("Warning: Graph is not connected. Simplifying to the largest connected component.")
                # Get the nodes of the largest connected component
                largest_component_nodes = max(nx.connected_components(undirected_G), key=len)
                # Create a subgraph containing only these nodes and their edges
                self.G = self.G.subgraph(largest_component_nodes)
                print(f"Graph simplified to its largest connected component with {len(self.G.nodes)} nodes.")
            else:
                print("Graph is connected.")

            # Save the constructed graph to graphml for future use
            ox.save_graphml(self.G, self.osmnx_graph_path)
            print(f"OSMnx graph saved to {self.osmnx_graph_path} for faster loading next time.")

            # Ensure the graph has a 'bbox' attribute
            x_coords = [data['x'] for node, data in self.G.nodes(data=True)]
            y_coords = [data['y'] for node, data in self.G.nodes(data=True)]
            self.G.graph['bbox'] = (min(x_coords), max(x_coords), min(y_coords), max(y_coords)) # (min_lon, max_lon, min_lat, max_lat)

        # Initialize CRS transformers for coordinate conversions
        self.crs_transformer_to_proj = pyproj.Transformer.from_crs(self.INPUT_LONLAT_CRS, self.PROJECTED_CRS, always_xy=True)
        self.crs_transformer_to_lonlat = pyproj.Transformer.from_crs(self.PROJECTED_CRS, self.INPUT_LONLAT_CRS, always_xy=True)

        # Ensure the graph has a 'bbox' attribute (min_lon, max_lon, min_lat, max_lat)
        if 'bbox' not in self.G.graph:
            x_coords = [data['x'] for node, data in self.G.nodes(data=True)]
            y_coords = [data['y'] for node, data in self.G.nodes(data=True)]
            self.G.graph['bbox'] = (min(x_coords), max(x_coords), min(y_coords), max(y_coords))

    def get_network_center(self):
        """Returns the central (lat, lon) coordinates of the network."""
        min_lon, max_lon, min_lat, max_lat = self.G.graph['bbox']
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
        return center_lat, center_lon

    def get_network_bbox(self):
        """Returns the bounding box (min_lat, max_lat, min_lon, max_lon) of the network."""
        min_lon, max_lon, min_lat, max_lat = self.G.graph['bbox']
        return min_lat, max_lat, min_lon, max_lon

    def lon_lat_to_node_id(self, lon, lat):
        """Converts lon/lat to the nearest OSMnx graph node ID."""
        # ox.nearest_nodes expects (Y, X) i.e., (latitude, longitude)
        node_id = ox.nearest_nodes(self.G, lat, lon) # Corrected order: lat, lon
        return node_id

    def _get_route_polyline_from_node_ids(self, orig_node, dest_node):
        """Internal helper to calculate a route between two OSMnx node IDs and returns the polyline with cumulative times."""
        if orig_node == dest_node:
            node_data = self.G.nodes[orig_node]
            return [(node_data['x'], node_data['y'], 0.0), (node_data['x'], node_data['y'], 0.0)]

        try:
            route = nx.shortest_path(self.G, orig_node, dest_node, weight='travel_time')
        except nx.NetworkXNoPath:
            print(f"Warning: No path found between OSMnx node {orig_node} and {dest_node}.")
            return []

        full_route_with_times = []
        cumulative_time = 0.0

        for i, node in enumerate(route):
            node_data = self.G.nodes[node]
            full_route_with_times.append((node_data['x'], node_data['y'], cumulative_time))

            if i < len(route) - 1:
                next_node = route[i+1]
                # Assuming the graph is not a MultiGraph or we take the first edge if it is
                edge_data = self.G.get_edge_data(node, next_node)
                if isinstance(edge_data, dict):
                    # For MultiGraph, get_edge_data returns a dict of edges for (u,v)
                    # We assume key 0 if not specified, or pick the first one
                    edge_data = edge_data.get(0, edge_data[list(edge_data.keys())[0]])
                
                edge_travel_time = edge_data.get('travel_time', 0) # Default to 0 if not found

                # Add intermediate points from the edge geometry
                if 'geometry' in edge_data and isinstance(edge_data['geometry'], LineString):
                    line = edge_data['geometry']
                    coords = list(line.coords)
                    # The first point is already added as part of the node_data above
                    # We need to distribute edge_travel_time over these segments
                    total_line_length = line.length

                    # Start from the second coordinate as the first is the start node
                    start_coord_idx = 1 if len(full_route_with_times) > 1 and coords[0] == (full_route_with_times[-1][0], full_route_with_times[-1][1]) else 0

                    for j in range(start_coord_idx, len(coords)):
                        current_point = coords[j]
                        previous_point = coords[j-1] if j > 0 else (full_route_with_times[-1][0], full_route_with_times[-1][1]) if full_route_with_times else (self.G.nodes[node]['x'], self.G.nodes[node]['y'])
                        
                        # Calculate segment length. Use Point objects for distance calculation.
                        segment_length = Point(previous_point).distance(Point(current_point))
                        
                        proportional_time = (segment_length / total_line_length) * edge_travel_time if total_line_length > 0 else 0
                        
                        cumulative_time += proportional_time
                        full_route_with_times.append((current_point[0], current_point[1], cumulative_time))
                else:
                    # Fallback: if no geometry, just add the travel time to the next node
                    cumulative_time += edge_travel_time
                    # The next node will be added in the next iteration, its position will be updated with this cumulative_time

        return full_route_with_times

    def get_route_polyline_from_coords(self, start_lon, start_lat, end_lon, end_lat):
        """Calculates a route between two lon/lat points and returns the polyline as a list of (lon, lat, cumulative_time) tuples."""
        orig_node = self.lon_lat_to_node_id(start_lon, start_lat)
        dest_node = self.lon_lat_to_node_id(end_lon, end_lat)
        
        # Check if orig_node or dest_node is None (e.g., if coordinates are too far from network)
        if orig_node is None or dest_node is None:
            print(f"Warning: Could not find nearest node for coordinates: ({start_lon}, {start_lat}) or ({end_lon}, {end_lat})")
            return []

        # Handle case where start and end points map to the same node
        if orig_node == dest_node:
            node_data = self.G.nodes[orig_node]
            # Return two identical points with 0 cumulative time if start and end are the same node
            return [(node_data['x'], node_data['y'], 0.0), (node_data['x'], node_data['y'], 0.0)]
        
        return self._get_route_polyline_from_node_ids(orig_node, dest_node)

    def get_interpolated_position(self, polyline, current_time):
        """
        Interpolates the position (lon, lat) along a polyline at a given current_time.
        The polyline is a list of (lon, lat, cumulative_time) tuples.
        """
        if not polyline:
            return None, None

        # If current_time is before the start of the polyline, return the start position
        if current_time <= polyline[0][2]:
            return polyline[0][0], polyline[0][1]
        # If current_time is after the end of the polyline, return the end position
        if current_time >= polyline[-1][2]:
            return polyline[-1][0], polyline[-1][1]

        # Find the segment where current_time falls
        for i in range(len(polyline) - 1):
            start_point = polyline[i]
            end_point = polyline[i+1]

            if start_point[2] <= current_time <= end_point[2]:
                segment_duration = end_point[2] - start_point[2]
                
                # If segment_duration is 0, it means start and end points are the same time-wise.
                # Just return the start_point coordinates.
                if segment_duration == 0:
                    return start_point[0], start_point[1]

                # Calculate the proportion of the segment covered at current_time
                proportion = (current_time - start_point[2]) / segment_duration

                # Interpolate longitude and latitude
                lon = start_point[0] + proportion * (end_point[0] - start_point[0])
                lat = start_point[1] + proportion * (end_point[1] - start_point[1])
                return lon, lat
        
        return None, None # Should not happen if current_time is within polyline times
