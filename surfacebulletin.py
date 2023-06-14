import cartopy.crs as ccrs
import cartopy.feature as cfeat
import matplotlib.pyplot as plt
import urllib.request
from io import BytesIO
from metpy.io import parse_wpc_surface_bulletin
from metpy.plots import ColdFront, OccludedFront, StationaryFront, StationPlot, WarmFront
from os import path, listdir
from pathlib import Path


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
    if path.exists(gisSaveDir) and path.exists(staticSaveDir):
        filesInTargets = listdir(gisSaveDir)
        filesInTargets.extend(listdir(staticSaveDir))
        if len(filesInTargets) > 0:
            exit()
    # Set up a default figure and map
    gisFig = plt.figure()
    gisAx = plt.axes(projection=ccrs.epsg(3857))
    gisAx.set_extent([-130, -60, 20, 50], crs=ccrs.PlateCarree())
    fig = plt.figure()
    ax = plt.axes(projection=ccrs.LambertConformal())
    ax.set_extent([-130, -60, 20, 50], crs=ccrs.PlateCarree())
 
    plot_bulletin(gisAx, df)
    plot_bulletin(ax, df)

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

    ax.add_feature(cfeat.STATES.with_scale("50m"), linewidth=0.5)
    ax.add_feature(cfeat.COASTLINE.with_scale("50m"), linewidth=0.5)
    Path(staticSaveDir).mkdir(parents=True, exist_ok=True)
    if hasHelpers:
        HDWX_helpers.writeJson(basePath, 1201, validTime.replace(minute=0), validTime.strftime("%H%M.png"), validTime, ["0,0", "0,0"], 300)
        HDWX_helpers.dressImage(fig, ax, f"WPC Surface Analysis", validTime)
        HDWX_helpers.saveImage(fig, path.join(staticSaveDir, validTime.strftime("%H%M.png")))
    else:
        fig.savefig(path.join(staticSaveDir, validTime.strftime("%H%M.png")))

