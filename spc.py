#!/usr/bin/env python3
# Plots SPC outlooks for python HDWX
# Created 22 June 2023 by Sam Gardner <stgardner4@tamu.edu>

import geopandas
import requests
from os import path, listdir, remove
from pathlib import Path
import zipfile
from io import BytesIO
from cartopy import crs as ccrs
from cartopy import feature as cfeat
from matplotlib import pyplot as plt
from matplotlib.patches import Patch
from datetime import datetime as dt
import pandas as pd
from shutil import rmtree

basePath = path.realpath(path.dirname(__file__))
axExtent = [-130, -60, 20, 50]

hasHelpers = False
if path.exists(path.join(basePath, "HDWX_helpers.py")):
    hasHelpers = True
    import HDWX_helpers

def plotOutlook(data, dayNum, startTime, finalTime, issueTime, outlookType):
    legend_elements = []
    if outlookType == "cat":
        legend_elements.append(Patch(facecolor="#00000000", edgecolor="#00000000", label="Classification Info:\nhttps://www.spc.noaa.gov/misc/SPC_probotlk_info.html"))
        prettyOutlookType = "Categorical"
    elif outlookType == "hail":
        legend_elements.append(Patch(facecolor="#00000000", edgecolor="#00000000", label="Chance of Hail >= 1\" within 25 miles of a point"))
        prettyOutlookType = "Hail"
        sigRisk = "(2\" or larger)"
    elif outlookType == "torn":
        legend_elements.append(Patch(facecolor="#00000000", edgecolor="#00000000", label="Chance of Tornado within 25 miles of a point"))
        prettyOutlookType = "Tornado"
        sigRisk = "(EF2 or stronger)"
    elif outlookType == "wind":
        legend_elements.append(Patch(facecolor="#00000000", edgecolor="#00000000", label="Chance of Wind >= 58 mph within 25 miles of a point"))
        prettyOutlookType = "Wind"
        sigRisk = "(74 mph or stronger)"
    elif outlookType == "prob":
        legend_elements.append(Patch(facecolor="#00000000", edgecolor="#00000000", label="Chance of any severe weather within 25 miles of a point"))
        prettyOutlookType = "Probabilistic"
        sigRisk = "(10% chance of 2\" or larger hail, or EF2 or stronger tornado, or 74 mph or stronger wind)"
    elif outlookType == "fire":
        legend_elements.append(Patch(facecolor="#00000000", edgecolor="#00000000", label="Classification Info:\nhttps://www.spc.noaa.gov/misc/about.html#FireWx"))
        prettyOutlookType = "Fire Weather"
        sigRisk = ""
    fig = plt.figure()
    px = 1/plt.rcParams["figure.dpi"]
    fig.set_size_inches(1920*px, 1080*px)
    ax = plt.axes(projection=ccrs.LambertConformal())
    ax.set_extent(axExtent, crs=ccrs.PlateCarree())
    for dnval in data["DN"].unique():
        polysForCat = data[data["DN"] == dnval]
        if len(polysForCat) == 0:
            continue
        if dnval == 0:
            continue
        fcolor = str(polysForCat["fill"].iloc[0])
        ecolor = str(polysForCat["stroke"].iloc[0])
        label = str(polysForCat["LABEL2"].iloc[0]).replace("General ", "").replace("s Risk", "").replace(" Hail", "").replace(" Tornado", "").replace(" Wind", "").replace(" Fire", "").replace(" Risk", "")
        if "Significant" in label:
            ax.add_geometries(polysForCat["geometry"], crs=ccrs.PlateCarree(), facecolor="#00000000", edgecolor=ecolor, linewidth=1, hatch="///")
            legend_elements.append(Patch(facecolor="#00000000", edgecolor=ecolor, hatch="///", label=f"{label} {sigRisk}"))
        else:
            ax.add_geometries(polysForCat["geometry"], crs=ccrs.PlateCarree(), facecolor=fcolor, edgecolor=ecolor, linewidth=0.75)

            legend_elements.append(Patch(facecolor=fcolor, edgecolor=ecolor, label=label))
    ax.add_feature(cfeat.STATES.with_scale("50m"), linewidth=0.5)
    ax.add_feature(cfeat.COASTLINE.with_scale("50m"), linewidth=0.5)
    if len(legend_elements) == 1:
        ax.text(0.5, 0.5, "No areas", transform=ax.transAxes, ha="center", va="center")
    else:
        ax.legend(handles=legend_elements, loc="lower right")
    savePaths = {}
    if hasHelpers:
        HDWX_helpers.dressImage(fig, ax, f"SPC Day {dayNum} {prettyOutlookType} Outlook", startTime)
        fig.axes[1].get_children()[0].set_text(f"{fig.axes[1].get_children()[0].get_text()} through {finalTime.strftime('%a %-d %b %Y %H%MZ')}")
    if outlookType == "cat":
            savePaths["1203"] = path.join(basePath, "output", "products", "noaa", "spc", "catout")
            savePaths["1205"] = path.join(basePath, "output", "products", "noaa", "spc", "LRout")
    elif outlookType == "prob":
            if dayNum >=4:
                savePaths["1205"] = path.join(basePath, "output", "products", "noaa", "spc", "LRout")
            savePaths["1207"] = path.join(basePath, "output", "products", "noaa", "spc", "probout")
    elif outlookType == "hail":
        savePaths["1209"] = path.join(basePath, "output", "products", "noaa", "spc", "hailout")
    elif outlookType == "wind":
        savePaths["1211"] = path.join(basePath, "output", "products", "noaa", "spc", "windout")
    elif outlookType == "torn":
        savePaths["1213"] = path.join(basePath, "output", "products", "noaa", "spc", "tornout")
    elif outlookType == "fire":
        savePaths["1215"] = path.join(basePath, "output", "products", "noaa", "spc", "fireout")
    for productID in savePaths.keys():
        savePath = savePaths[productID]
        productID = int(productID)
        savePath = path.join(savePath, issueTime.strftime("%Y"), issueTime.strftime("%m"), issueTime.strftime("%d"), issueTime.strftime("%H00"))
        Path(savePath).mkdir(parents=True, exist_ok=True)
        if hasHelpers:
            HDWX_helpers.writeJson(basePath, productID, issueTime.replace(minute=0).replace(second=0), f"day{dayNum}.png", finalTime, ["0,0", "0,0"], 3600)
            HDWX_helpers.saveImage(fig, path.join(savePath, f"day{dayNum}.png"))
        else:
            fig.savefig(path.join(savePath, f"day{dayNum}.png"))
    plt.close(fig)




if __name__ == "__main__":
    lastUpdateCheckPage = pd.read_html("https://www.spc.noaa.gov/products/outlook/")[5]
    issueTime = dt.strptime(lastUpdateCheckPage[1].iloc[1].split("document.write")[0].replace(f" {str(int(dt.utcnow().strftime('%d')))} ", f" {dt.utcnow().strftime('%d')} "), f"Updated: %a %b %d %H:%M:%S UTC %Y")
    if path.exists(path.join(basePath, "output", "metadata", "products", "1213", issueTime.strftime("%Y%m%d%H00.json"))):
        exit()
    inputPath = path.join(basePath, "input")
    Path(inputPath).mkdir(parents=True, exist_ok=True)
    for dayNum in range(1, 9):
        convDayInputPath = path.join(inputPath, f"day{dayNum}-conv")
        Path(convDayInputPath).mkdir(parents=True, exist_ok=True)
        if dayNum < 4:
            file = requests.get(f"https://www.spc.noaa.gov/products/outlook/day{dayNum}otlk-shp.zip")
        else:
            file = requests.get(f"https://www.spc.noaa.gov/products/exper/day4-8/day{dayNum}prob-shp.zip")
        z = zipfile.ZipFile(BytesIO(file.content))
        z.extractall(convDayInputPath)
        filesInTarget = listdir(convDayInputPath)
        infoFile = None
        shapeFiles = []
        for file in filesInTarget:
            if file.endswith(".info"):
                infoFile = file
            elif file.endswith(".shp"):
                shapeFiles.append(file)
        with open(path.join(convDayInputPath, infoFile), "r") as infoFileHandle:
            infoLines = infoFileHandle.readlines()
        startTime = dt.strptime(infoLines[0], "Product Valid Time Begin: %Y-%m-%d %H:%M:%S+00:00\n")
        endTime =  dt.strptime(infoLines[1], "Product Valid Time End: %Y-%m-%d %H:%M:%S+00:00\n")
        for shapeFile in shapeFiles:
            outlookType = shapeFile.split("_")[-1].lower().replace(".shp", "")
            if "sig" in outlookType:
                continue
            gpdata = geopandas.read_file(path.join(convDayInputPath, shapeFile))
            plotOutlook(gpdata, dayNum, startTime, endTime, issueTime, outlookType)
    for dayNum in range(1, 9):
        convDayInputPath = path.join(inputPath, f"day{dayNum}-fire")
        Path(convDayInputPath).mkdir(parents=True, exist_ok=True)
        if dayNum < 3:
            file = requests.get(f"https://www.spc.noaa.gov/products/fire_wx/day{dayNum}firewx-shp.zip")
        else:
            file = requests.get(f"https://www.spc.noaa.gov/products/exper/fire_wx/day{dayNum}firewx-shp.zip")
        z = zipfile.ZipFile(BytesIO(file.content))
        z.extractall(convDayInputPath)
        filesInTarget = listdir(convDayInputPath)
        infoFile = None
        shapeFiles = []
        for file in filesInTarget:
            if file.endswith(".info"):
                infoFile = file
            elif file.endswith(".shp"):
                shapeFiles.append(file)
        with open(path.join(convDayInputPath, infoFile), "r") as infoFileHandle:
            infoLines = infoFileHandle.readlines()
        startTime = dt.strptime(infoLines[0], "Product Valid Time Begin: %Y-%m-%d %H:%M:%S+00:00\n")
        endTime =  dt.strptime(infoLines[1], "Product Valid Time End: %Y-%m-%d %H:%M:%S+00:00\n")
        for shapeFile in shapeFiles:
            if "dryltg" in shapeFile:
                continue
            gpdata = geopandas.read_file(path.join(convDayInputPath, shapeFile))
            plotOutlook(gpdata, dayNum, startTime, endTime, issueTime, "fire")
    rmtree(path.join(basePath, "input"))
    