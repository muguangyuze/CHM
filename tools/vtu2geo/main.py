import vtk
import sys
from osgeo import gdal,ogr,osr
import glob
import imp
import sys
import xml.etree.ElementTree as ET

# Print iterations progress
# http://stackoverflow.com/a/34325723/410074
def printProgress(iteration, total, prefix='', suffix='', decimals=2, barLength=100):
    """
    Call in a loop to create terminal progress bar
    @params:
        iterations  - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
    """
    filledLength = int(round(barLength * iteration / float(total)))
    percents = round(100.00 * (iteration / float(total)), decimals)
    bar = '#' * filledLength + '-' * (barLength - filledLength)
    sys.stdout.write('%s [%s] %s%s %s\r' % (prefix, bar, percents, '%', suffix)),
    sys.stdout.flush()
    if iteration == total:
        print("\n")


def main():
    gdal.UseExceptions()  # Enable errors
    
    #####  load user configurable paramters here    #######
    # Check user defined configuraiton file
    if len(sys.argv) == 1:
        print('ERROR: main.py requires one argument [configuration file] (i.e. python main.py vtu2geo.py)')
        return

    # Get name of configuration file/module
    configfile = sys.argv[-1]

    # Load in configuration file as module
    X = imp.load_source('',configfile)

    # Grab variables
    base = X.base
    input_path = X.input_path
    # EPSG = X.EPSG
    variables = X.variables
    parameters = X.parameters
    pixel_size = X.pixel_size

    is_geographic = False
    if hasattr(X,'is_geographic'):
        is_geographic = X.is_geographic

    #####
    reader = vtk.vtkXMLUnstructuredGridReader()
    pvd = ET.parse(input_path)
    pvd = pvd.findall(".//*[@file]")

    iter=1
    for vtu in pvd:

        path = input_path[:input_path.rfind('/')+1] + vtu.get('file')
        printProgress(iter,len(pvd))
        reader.SetFileName(path)
        reader.Update()

        mesh = reader.GetOutput()

        driver = ogr.GetDriverByName('Memory')
        # driver = ogr.GetDriverByName("ESRI Shapefile")
        # output_usm = driver.CreateDataSource('lol.shp')
        output_usm = driver.CreateDataSource('out')

        # srsin.ImportFromEPSG(EPSG)

        srsin = osr.SpatialReference()
        srsin.ImportFromWkt("PROJCS[\"North_America_Albers_Equal_Area_Conic\",     "
                             "GEOGCS[\"GCS_North_American_1983\",         "
                             "DATUM[\"North_American_Datum_1983\",            "
                             " SPHEROID[\"GRS_1980\",6378137,298.257222101]],         "
                             "PRIMEM[\"Greenwich\",0],        "
                             " UNIT[\"Degree\",0.017453292519943295]],     "
                             "PROJECTION[\"Albers_Conic_Equal_Area\"],     "
                             "PARAMETER[\"False_Easting\",0],    "
                             " PARAMETER[\"False_Northing\",0],     "
                             "PARAMETER[\"longitude_of_center\",-96],     "
                             "PARAMETER[\"Standard_Parallel_1\",20],     "
                             "PARAMETER[\"Standard_Parallel_2\",60],     "
                             "PARAMETER[\"latitude_of_center\",40],     "
                             "UNIT[\"Meter\",1],     "
                             "AUTHORITY[\"EPSG\",\"102008\"]]")

        #output conic equal area for geotiff if we have geographic input
        srsout = osr.SpatialReference()
        srsout.ImportFromWkt("PROJCS[\"North_America_Albers_Equal_Area_Conic\",     "
                             "GEOGCS[\"GCS_North_American_1983\",         "
                             "DATUM[\"North_American_Datum_1983\",            "
                             " SPHEROID[\"GRS_1980\",6378137,298.257222101]],         "
                             "PRIMEM[\"Greenwich\",0],        "
                             " UNIT[\"Degree\",0.017453292519943295]],     "
                             "PROJECTION[\"Albers_Conic_Equal_Area\"],     "
                             "PARAMETER[\"False_Easting\",0],    "
                             " PARAMETER[\"False_Northing\",0],     "
                             "PARAMETER[\"longitude_of_center\",-96],     "
                             "PARAMETER[\"Standard_Parallel_1\",20],     "
                             "PARAMETER[\"Standard_Parallel_2\",60],     "
                             "PARAMETER[\"latitude_of_center\",40],     "
                             "UNIT[\"Meter\",1],     "
                             "AUTHORITY[\"EPSG\",\"102008\"]]")
        trans = osr.CoordinateTransformation(srsin,srsout)

        layer = output_usm.CreateLayer('poly', srsout, ogr.wkbPolygon)

        cd = mesh.GetCellData()


        for i in range(0,cd.GetNumberOfArrays()):
            # print cd.GetArrayName(i)
            layer.CreateField(ogr.FieldDefn(cd.GetArrayName(i), ogr.OFTReal))

        #build the triangulation geometery
        for i in range(0, mesh.GetNumberOfCells()):
            v0 = mesh.GetCell(i).GetPointId(0)
            v1 = mesh.GetCell(i).GetPointId(1)
            v2 = mesh.GetCell(i).GetPointId(2)

            ring = ogr.Geometry(ogr.wkbLinearRing)
            if is_geographic:
                scale = 100000.  #undo the scaling that CHM does for the paraview output
                ring.AddPoint( mesh.GetPoint(v0)[0] / scale, mesh.GetPoint(v0)[1] / scale)
                ring.AddPoint (mesh.GetPoint(v1)[0]/ scale, mesh.GetPoint(v1)[1]/ scale )
                ring.AddPoint( mesh.GetPoint(v2)[0]/ scale, mesh.GetPoint(v2)[1]/ scale )
                ring.AddPoint( mesh.GetPoint(v0)[0]/ scale, mesh.GetPoint(v0)[1]/ scale ) # add again to complete the ring.

                ring.Transform(trans)
            else:
                ring.AddPoint( mesh.GetPoint(v0)[0], mesh.GetPoint(v0)[1] )
                ring.AddPoint (mesh.GetPoint(v1)[0], mesh.GetPoint(v1)[1] )
                ring.AddPoint( mesh.GetPoint(v2)[0], mesh.GetPoint(v2)[1] )
                ring.AddPoint( mesh.GetPoint(v0)[0], mesh.GetPoint(v0)[1] ) # add again to complete the ring.

            tpoly = ogr.Geometry(ogr.wkbPolygon)
            tpoly.AddGeometry(ring)

            feature = ogr.Feature( layer.GetLayerDefn() )
            feature.SetGeometry(tpoly)

            if variables is None:
                for j in range(0, cd.GetNumberOfArrays()):
                    name = cd.GetArrayName(j)
                    variables.append(name)

            for v in variables:
                data = cd.GetArray(v).GetTuple(i)
                feature.SetField(str(v), float(data[0]))

            if parameters is not None:
                for p in parameters:
                    data = cd.GetArray(p).GetTuple(i)
                    feature.SetField(str(p), float(data[0]))


            layer.CreateFeature(feature)


        x_min, x_max, y_min, y_max = layer.GetExtent()


        NoData_value = -9999
        x_res = int((x_max - x_min) / pixel_size)
        y_res = int((y_max - y_min) / pixel_size)

        for var in variables:
            target_ds = gdal.GetDriverByName('GTiff').Create(path[:-4]+'_'+var+'.tif', x_res, y_res, 1, gdal.GDT_Float32)
            target_ds.SetGeoTransform((x_min, pixel_size, 0, y_max, 0, -pixel_size))
            # target_ds.SetProjection(srs)
            band = target_ds.GetRasterBand(1)

            band.SetNoDataValue(NoData_value)

            # Rasterize
            gdal.RasterizeLayer(target_ds, [1], layer, burn_values=[0],options=['ALL_TOUCHED=TRUE',"ATTRIBUTE="+var])
            target_ds.SetProjection(srsout.ExportToWkt())
            target_ds = None

        if parameters is not None:
            for p in parameters:
                target_ds = gdal.GetDriverByName('GTiff').Create(path[:-4] + '_' + p + '.tif', x_res, y_res, 1,
                                                                 gdal.GDT_Float32)
                target_ds.SetGeoTransform((x_min, pixel_size, 0, y_max, 0, -pixel_size))
                target_ds.SetProjection(srsout.ExportToWkt())
                band = target_ds.GetRasterBand(1)
                band.SetNoDataValue(NoData_value)

                # Rasterize
                gdal.RasterizeLayer(target_ds, [1], layer, burn_values=[0],options=['ALL_TOUCHED=TRUE', "ATTRIBUTE=" + p])
                target_ds = None

            parameters = None

        iter += 1

if __name__ == "__main__":

    main()
