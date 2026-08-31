# Reference Data Audit

Reference processed file

reference_data/processed/seoul_network.json

Reference manifest

reference_data/manifests/reference_data_manifest.json

The processed file contains WGS84 station coordinates, OSM bus stop coordinates, public bus route identifiers, station lists grouped by stored line key, and 12 OSRM surface corridor geometries derived from OpenStreetMap.

Station records

line_1: 6 selected station records
line_2: 12 selected station records
line_3: 8 selected station records
line_4: 5 selected station records
line_5: 5 selected station records
line_6: 5 selected station records
line_7: 4 selected station records
line_9: 5 selected station records

Bus route records

143: 4 OSM stop positions, source note: public route identifier with OSM stop geometry corridor sample
402: 4 OSM stop positions, source note: public route identifier with OSM stop geometry corridor sample
421: 4 OSM stop positions, source note: public route identifier with OSM stop geometry corridor sample
740: 4 OSM stop positions, source note: public route identifier with OSM stop geometry corridor sample
7016: 4 OSM stop positions, source note: public route identifier with OSM stop geometry corridor sample

Rail source status

RAIL POLYLINE REFERENCE = NOT AVAILABLE

The rail data is station point data grouped into compact stored sequences. It does not contain rail way geometry, track polylines, timetable data, or a complete authoritative station sequence for every line.

Bus source status

The official Seoul bus source URLs are recorded in the manifest, but the processed file does not contain the official Seoul route file. The current records are public route identifiers plus nearest OSM stop positions selected from anchor points. Official route membership and stop order are not verifiable from this repository alone.

Surface source status

The surface corridors are precomputed OSRM driving geometries based on OpenStreetMap. They are actual OSM derived road route shapes for the stored origin and destination hub pairs. They are not a complete Seoul road graph and are reused by walk and bike generation.
