#!/usr/bin/env python3
# Recreates WPC surface analysis from WPC bulletin, METARs, and RTMA pressure data
# Created 14 June 2023 by Sam Gardner <stgardner4@tamu.edu>

import cartopy.crs as ccrs
import cartopy.feature as cfeat
import matplotlib.pyplot as plt
import urllib
from io import BytesIO
import metpy
from metpy.io import parse_wpc_surface_bulletin
from metpy.io import parse_metar_file
from metpy.units import pandas_dataframe_to_unit_arrays
from metpy import calc as mpcalc
from metpy import plots as mpplots
from metpy.units import units
from metpy.plots import ColdFront, OccludedFront, StationaryFront, StationPlot, WarmFront
from metpy.cbook import get_test_data
from metpy import constants
from os import path, listdir, remove
from pathlib import Path
from siphon.catalog import TDSCatalog
import pandas as pd
from matplotlib.patheffects import withStroke
import xarray as xr
import numpy as np
from scipy import ndimage
import sys


basePath = path.realpath(path.dirname(__file__))
hasHelpers = False
if path.exists(path.join(basePath, "HDWX_helpers.py")):
    import HDWX_helpers
    hasHelpers = True


def set_size(w,h, ax=None):
    if not ax: ax=plt.gca()
    l = ax.figure.subplotpars.left
    r = ax.figure.subplotpars.right
    t = ax.figure.subplotpars.top
    b = ax.figure.subplotpars.bottom
    figw = float(w)/(r-l)
    figh = float(h)/(t-b)
    ax.figure.set_size_inches(figw, figh)



def addRTMAPressure(ax, validTime):
    rtmaLink = f"https://nomads.ncep.noaa.gov/cgi-bin/filter_rtma2p5.pl?dir=%2Frtma2p5.{validTime.strftime('%Y%m%d')}&file=rtma2p5.t{validTime.strftime('%H')}z.2dvaranl_ndfd.grb2_wexp&var_HGT=on&var_PRES=on&var_TMP=on&lev_2_m_above_ground=on&lev_surface=on"
    urllib.request.urlretrieve(rtmaLink, "rtma.grib2")
    rtmaData = xr.open_dataset("rtma.grib2", engine="cfgrib", backend_kwargs={"indexpath" : ""})
    orogData = rtmaData.orog.metpy.quantify()
    barometricPressData = rtmaData.sp.metpy.quantify()
    tempData = rtmaData.t2m.metpy.quantify()
    mslpData = barometricPressData * np.exp(orogData*constants.earth_gravity/(constants.dry_air_gas_constant*tempData))
    mslpData = mslpData.metpy.convert_units("hPa")
    mslpData.data = ndimage.gaussian_filter(mslpData.data, 20)
    levelsToContour = np.arange((np.nanmin(mslpData.data) // 4) * 4, np.nanmax(mslpData.data)+4, 4)
    contourmap = ax.contour(mslpData.longitude, mslpData.latitude, mslpData, colors="maroon", levels=levelsToContour, transform=ccrs.PlateCarree(), transform_first=True, linewidths=0.5)
    contourLabels = ax.clabel(contourmap, levels=levelsToContour, fontsize=8, inline_spacing=-9)
    remove("rtma.grib2")
    return ax


def addStationPlot(ax, validTime):
    metarTime = validTime.replace(minute=0, second=0, microsecond=0)
    stationCatalog = TDSCatalog("https://thredds.ucar.edu/thredds/catalog/noaaport/text/metar/catalog.xml")
    airports = pd.read_csv(get_test_data("airport-codes.csv"))
    airports = airports[(airports["type"] == "large_airport") | (airports["type"] == "medium_airport") | (airports["type"] == "small_airport")]
    try:
        dataset = stationCatalog.datasets.filter_time_nearest(metarTime)
        dataset.download()
        [remove(file) for file in sorted(listdir()) if "metar_" in file and file != dataset.name]
    except Exception as e:
        print(stationCatalog.datasets.filter_time_nearest(metarTime).remote_open().read())
    if path.exists(dataset.name):
        metarData = parse_metar_file(dataset.name, year=metarTime.year, month=metarTime.month)
    else:
        return
    metarUnits = metarData.units

    metarDataFilt = metarData[metarData["station_id"].isin(airports["ident"])]
    metarDataFilt = metarDataFilt.dropna(how="any", subset=["longitude", "latitude", "station_id", "wind_speed", "wind_direction", "air_temperature", "dew_point_temperature", "air_pressure_at_sea_level", "current_wx1_symbol", "cloud_coverage"])
    metarDataFilt = metarDataFilt.drop_duplicates(subset=["station_id"], keep="last")
    metarData = pandas_dataframe_to_unit_arrays(metarDataFilt, metarUnits)
    metarData["u"], metarData["v"] = mpcalc.wind_components(metarData["wind_speed"], metarData["wind_direction"])
    locationsInMeters = ccrs.LambertConformal().transform_points(ccrs.PlateCarree(), metarData["longitude"].m, metarData["latitude"].m)
    overlap_prevent = mpcalc.reduce_point_density(locationsInMeters[:, 0:2], 200000)
    stations = mpplots.StationPlot(ax, metarData["longitude"][overlap_prevent], metarData["latitude"][overlap_prevent], clip_on=True, transform=ccrs.PlateCarree(), fontsize=6)
    stations.plot_parameter("NW", metarData["air_temperature"][overlap_prevent].to(units.degF), path_effects=[withStroke(linewidth=1, foreground="white")])
    stations.plot_parameter("SW", metarData["dew_point_temperature"][overlap_prevent].to(units.degF), path_effects=[withStroke(linewidth=1, foreground="white")])
    stations.plot_parameter("NE", metarData["air_pressure_at_sea_level"][overlap_prevent].to(units.hPa), formatter=lambda v: format(10 * v, '.0f')[-3:], path_effects=[withStroke(linewidth=1, foreground="white")])
    stations.plot_symbol((-1.5, 0), metarData['current_wx1_symbol'][overlap_prevent], mpplots.current_weather, path_effects=[withStroke(linewidth=1, foreground="white")], fontsize=9)
    stations.plot_symbol("C", metarData["cloud_coverage"][overlap_prevent], mpplots.sky_cover)
    stations.plot_barb(metarData["u"][overlap_prevent], metarData["v"][overlap_prevent], sizes={"emptybarb" : 0})
    remove(dataset.name)
    return ax


def plot_bulletin(ax, data):
    """Plot a dataframe of surface features on a map."""
    # Set some default visual styling
    size = 4
    fontsize = 9
    complete_style = {"HIGH": {"color": "blue", "fontsize": fontsize},
                      "LOW": {"color": "red", "fontsize": fontsize},
                      "WARM": {"linewidth": 1, "path_effects": [WarmFront(size=size)]},
                      "COLD": {"linewidth": 1, "path_effects": [ColdFront(size=size)]},
                      "OCFNT": {"linewidth": 1, "path_effects": [OccludedFront(size=size)]},
                      "STNRY": {"linewidth": 1, "path_effects": [StationaryFront(size=size)]},
                      "TROF": {"linewidth": 2, "linestyle": "dashed",
                               "edgecolor": "darkorange"}}

    # Handle H/L points using MetPy's StationPlot class
    for field in ("HIGH", "LOW"):
        rows = data[data.feature == field]
        x, y = zip(*((pt.x, pt.y) for pt in rows.geometry))
        sp = StationPlot(ax, x, y, transform=ccrs.PlateCarree(), clip_on=True)
        sp.plot_text("C", [field[0]] * len(x), **complete_style[field])
        sp.plot_parameter("S", rows.strength, **complete_style[field])

    # Handle all the boundary types
    for field in ("WARM", "COLD", "STNRY", "OCFNT", "TROF"):
        rows = data[data.feature == field]
        ax.add_geometries(rows.geometry, crs=ccrs.PlateCarree(), **complete_style[field],
                          facecolor="none")



if __name__ == "__main__":
    # Parse the bulletin and plot it
    with urllib.request.urlopen("https://www.wpc.ncep.noaa.gov/discussions/codsus_hr") as response:
        df = BytesIO(response.read())
    df = parse_wpc_surface_bulletin(df)
    validTime = df.valid[0]
    gisSaveDir = path.join(basePath, "output", "gisproducts", "noaa", "wpcsfcbull", validTime.strftime("%Y"), validTime.strftime("%m"), validTime.strftime("%d"), validTime.strftime("%H00"))
    staticSaveDir = path.join(basePath, "output", "products", "noaa", "wpcsfcbull", validTime.strftime("%Y"), validTime.strftime("%m"), validTime.strftime("%d"), validTime.strftime("%H00"))
    if path.exists(gisSaveDir):
        filesInTargets = listdir(gisSaveDir)
        if len(filesInTargets) > 0:
            exit()
    if path.exists(staticSaveDir):
        filesInTargets = listdir(staticSaveDir)
        if len(filesInTargets) > 0:
            exit()
    # Set up a default figure and map
    if "--no-gis" not in sys.argv:
        gisFig = plt.figure()
        gisAx = plt.axes(projection=ccrs.epsg(3857))
        gisAx.set_extent([-130, -60, 20, 50], crs=ccrs.PlateCarree())
        plot_bulletin(gisAx, df)
        px = 1/plt.rcParams["figure.dpi"]
        set_size(1920*px, 1080*px, ax=gisAx)
        extent = gisAx.get_tightbbox(gisFig.canvas.get_renderer()).transformed(gisFig.dpi_scale_trans.inverted())
        Path(gisSaveDir).mkdir(parents=True, exist_ok=True)
        if hasHelpers:
            gisAxExtent = gisAx.get_extent(crs=ccrs.PlateCarree())
            HDWX_helpers.writeJson(basePath, 1200, validTime.replace(minute=0), validTime.strftime("%H%M.png"), validTime, [f"{gisAxExtent[2]},{gisAxExtent[0]}", f"{gisAxExtent[3]},{gisAxExtent[1]}"], 300)
            HDWX_helpers.saveImage(gisFig, path.join(gisSaveDir, validTime.strftime("%H%M.png")), transparent=True, bbox_inches=extent)
        else:
            gisFig.savefig(path.join(gisSaveDir, validTime.strftime("%H%M.png")), transparent=True, bbox_inches=extent) 
    fig = plt.figure()
    ax = plt.axes(projection=ccrs.LambertConformal())
    ax.set_extent([-130, -60, 20, 50], crs=ccrs.PlateCarree())
 
    addRTMAPressure(ax, validTime)
    addStationPlot(ax, validTime)
    plot_bulletin(ax, df)

    ax.add_feature(cfeat.STATES.with_scale("50m"), linewidth=0.5)
    ax.add_feature(cfeat.COASTLINE.with_scale("50m"), linewidth=0.5)
    Path(staticSaveDir).mkdir(parents=True, exist_ok=True)
    if hasHelpers:
        HDWX_helpers.writeJson(basePath, 1201, validTime.replace(minute=0), validTime.strftime("%H%M.png"), validTime, ["0,0", "0,0"], 300)
        HDWX_helpers.dressImage(fig, ax, f"WPC Surface Analysis", validTime)
        HDWX_helpers.saveImage(fig, path.join(staticSaveDir, validTime.strftime("%H%M.png")))
    else:
        fig.savefig(path.join(staticSaveDir, validTime.strftime("%H%M.png")))

