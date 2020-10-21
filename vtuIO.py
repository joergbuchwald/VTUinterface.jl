import os
import numpy as np
import pandas as pd
from vtk import *
from vtk.util.numpy_support import vtk_to_numpy
from vtk.util.numpy_support import numpy_to_vtk
from lxml import etree as ET
from scipy.interpolate import griddata


class VTUIO(object):
    def __init__(self, filename, dim=3):
        self.filename = filename
        self.reader = vtkXMLUnstructuredGridReader()
        self.reader.SetFileName(self.filename)
        self.reader.Update()
        self.output = self.reader.GetOutput()
        self.pdata = self.output.GetPointData()
        self.points = vtk_to_numpy(self.output.GetPoints().GetData())
        self.dim = dim
        if self.dim == 2:
            self.points = np.delete(self.points,2,1)

    def getNeighbors(self, points_interpol, numneighbors=20):
        df = pd.DataFrame(self.points)
        neighbors = {}
        for i, key in enumerate(points_interpol):
            if self.dim == 2:
                df["r_"+str(i)]=(df[0]-points_interpol[key][0])*(df[0]-points_interpol[key][0])+(df[1]-points_interpol[key][1])*(df[1]-points_interpol[key][1])
            else:
                df["r_"+str(i)]=(df[0]-points_interpol[key][0])*(df[0]-points_interpol[key][0])+(df[1]-points_interpol[key][1])*(df[1]-points_interpol[key][1])+(df[2]-points_interpol[key][2])*(df[2]-points_interpol[key][2])
            neighbors[i] = df.sort_values(by=["r_"+str(i)]).head(numneighbors).index
        return neighbors

    def getData(self, neighbors, points_interpol, fieldname):
        field = self.getField(fieldname)
        resp = {}
        for i, key in enumerate(points_interpol):
            if self.dim == 2:
                grid_x, grid_y = np.mgrid[points_interpol[key][0]:(points_interpol[key][0]+0.1):1, points_interpol[key][1]:(points_interpol[key][1]+0.1):1]
                resp[key] = griddata(self.points[neighbors[i]], field[neighbors[i]], (grid_x, grid_y), method='linear')[0][0]
            else:
                grid_x, grid_y, grid_z = np.mgrid[points_interpol[key][0]:(points_interpol[key][0]+0.1):1, points_interpol[key][1]:(points_interpol[key][1]+0.1):1, points_interpol[key][2]:(points_interpol[key][2]+0.1):]
                resp[key] = griddata(self.points[neighbors[i]], field[neighbors[i]], (grid_x, grid_y, grid_z), method='linear')[0][0][0]
        return resp

    def getField(self, fieldname):
        field = vtk_to_numpy(self.pdata.GetArray(fieldname))
        return field

    def getFieldnames(self):
        fieldnames = []
        for i in range(self.pdata.GetNumberOfArrays()):
            fieldnames.append(self.pdata.GetArrayName(i))
        return fieldnames

    def getPointData(self, fieldname, pts = {'pt0': (0.0,0.0,0.0)}):
        resp = {}
        for pt in pts:
            if type(fieldname) is str:
                resp[pt] = []
            elif type(fieldname) is list:
                resp[pt] = {}
                for field in fieldname:
                    resp[pt][field] = []
        nb = self.getNeighbors(pts)
        if type(fieldname) is str:
            data = self.getData(nb, pts, fieldname)
            for pt in pts:
                resp[pt]=data[pt]
        elif type(fieldname) is list:
            data = {}
            for field in fieldname:
                data[field] = self.getData(nb, pts, field)
            for pt in pts:
                for field in fieldname:
                    resp[pt][field]=data[field][pt]
        return resp

    def getPointSetData(self, fieldname, pointsetarray =[(0,0,0)]):
        pts = {}
        # convert into point dictionary
        for i, entry in enumerate(pointsetarray):
            pts['pt'+str(i)] = entry
        resp = self.getPointData(fieldname, pts=pts)
        resp_list = []
        # convert point dictionary into list
        for i, entry in enumerate(pointsetarray):
            resp_list.append(resp['pt'+str(i)])
        resp_array = np.array(resp_list)
        return resp_array


    def writeField(self, field, fieldname, ofilename):
        field_vtk = numpy_to_vtk(field)
        r = self.pdata.AddArray(field_vtk)
        self.pdata.GetArray(r).SetName(fieldname)
        writer = vtkXMLUnstructuredGridWriter()
        writer.SetFileName(ofilename)
        writer.SetInputData(self.output)
        writer.Write()



class PVDIO(object):
    def __init__(self, folder, filename, dim=3):
        self.folder = folder
        self.filename = ""
        self.ts_files = {}
        self.ts_files['ts'] = []
        self.ts_files['filename'] = []
        self.readPVD(os.path.join(folder,filename))
        self.dim = dim

    def readPVD(self,filename):
        print(filename)
        self.filename = filename
        tree = ET.parse(self.filename)
        root = tree.getroot()
        for collection in root.getchildren():
            for dataset in collection.getchildren():
                self.ts_files['ts'].append(float(dataset.attrib['timestep']))
                self.ts_files['filename'].append(dataset.attrib['file'])

    def readTimeSeries(self,fieldname, pts = {'pt0': (0.0,0.0,0.0)}):
        resp_t = {}
        for pt in pts:
            if type(fieldname) is str:
                resp_t[pt] = []
            elif type(fieldname) is list:
                resp_t[pt] = {}
                for field in fieldname:
                    resp_t[pt][field] = []
        for i, filename in enumerate(self.ts_files['filename']):
            vtu = VTUIO(os.path.join(self.folder,filename), dim=self.dim)
            if i == 0:
                nb = vtu.getNeighbors(pts)
            if type(fieldname) is str:
                data = vtu.getData(nb, pts, fieldname)
                for pt in pts:
                    resp_t[pt].append(data[pt])
            elif type(fieldname) is list:
                data = {}
                for field in fieldname:
                    data[field] = vtu.getData(nb, pts, field)
                for pt in pts:
                    for field in fieldname:
                        resp_t[pt][field].append(data[field][pt])
        return resp_t

    def readTimeStep(self, timestep, fieldname):
        filename = None
        for i, ts in enumerate(self.ts_files['ts']):
            if timestep == ts:
                filename = self.ts_files['filename'][i]
        if not filename is None:
            vtu = VTUIO(filename, dim=self.dim)
            field = vtu.getField(fieldname)
        else:
            filename1 = None
            filename2 = None
            timestep1 = 0.0
            timestep2 = 0.0
            for i, ts in enumerate(self.ts_files['ts']):
                try:
                    if (timestep > ts) and (timestep < self.ts_files['ts'][i+1]):
                        timestep1 = ts
                        timestep2 = self.ts_files['ts'][i+1]
                        filename1 = self.ts_files['filename'][i]
                        filename2 = self.ts_files['filename'][i+1]
                except IndexError:
                    print("time step is out of range")
            if (filename1 is None) or (filename2 is None):
                print("time step is out of range")
            else:
                vtu1 = VTUIO(filename1, dim=self.dim)
                vtu2 = VTUIO(filename2, dim=self.dim)
                field1 = vtu1.getField(fieldname)
                field2 = vtu2.getField(fieldname)
                fieldslope = (field2-field1)/(timestep2-timestep1)
                field = field1 + fieldslope * (timestep-timestep1)
        return field

    def readPointSetData(self, timestep, fieldname, pointsetarray =[(0,0,0)]):
        filename = None
        for i, ts in enumerate(self.ts_files['ts']):
            if timestep == ts:
                filename = self.ts_files['filename'][i]
        if not filename is None:
            vtu = VTUIO(filename, dim=self.dim)
            field = vtu.getPointSetData(fieldname, pointsetarray)
        else:
            filename1 = None
            filename2 = None
            timestep1 = 0.0
            timestep2 = 0.0
            for i, ts in enumerate(self.ts_files['ts']):
                try:
                    if (timestep > ts) and (timestep < self.ts_files['ts'][i+1]):
                        timestep1 = ts
                        timestep2 = self.ts_files['ts'][i+1]
                        filename1 = self.ts_files['filename'][i]
                        filename2 = self.ts_files['filename'][i+1]
                except IndexError:
                    print("time step is out of range")
            if (filename1 is None) or (filename2 is None):
                print("time step is out of range")
            else:
                vtu1 = VTUIO(filename1, dim=self.dim)
                vtu2 = VTUIO(filename2, dim=self.dim)
                field1 = vtu1.getPointSetData(fieldname, pointsetarray)
                field2 = vtu2.getPointSetData(fieldname, pointsetarray)
                fieldslope = (field2-field1)/(timestep2-timestep1)
                field = field1 + fieldslope * (timestep-timestep1)
        return field

    def clearPVDrelpath(self):
        xpath="./Collection/DataSet"
        tree = ET.parse(self.filename)
        root = tree.getroot()
        find_xpath = root.findall(xpath)
        for tag in find_xpath:
            filename = tag.get("file")
            filename_new = filename.split("/")[-1]
            tag.set("file", filename_new)
        tree.write(self.filename,
                            encoding="ISO-8859-1",
                            xml_declaration=True,
                            pretty_print=True)
        #update file list:
        newlist = []
        for entry in  self.ts_files['filename']:
            newlist.append(entry.split("/")[-1])
        self.ts_files['filename'] = newlist
