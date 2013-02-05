import os
import re
from xml.etree.ElementTree import Element, SubElement, tostring
from sextante.core.GeoAlgorithm import GeoAlgorithm
from sextante.parameters.ParameterRaster import ParameterRaster
from sextante.parameters.ParameterBoolean import ParameterBoolean
from sextante.parameters.ParameterSelection import ParameterSelection
from sextante.core.SextanteLog import SextanteLog
from sextante.parameters.ParameterFactory import ParameterFactory
from sextante.outputs.OutputFactory import OutputFactory
from sextante_gpf.GPFUtils import GPFUtils
from sextante_gpf.BEAMParametersDialog import BEAMParametersDialog
from sextante.parameters.ParameterExtent import ParameterExtent

class GPFAlgorithm(GeoAlgorithm):

    OUTPUT_EXTENT = "OUTPUT_EXTENT"

    NOVALUEINT = 99999
    NOVALUEDOUBLE = 99999.9

    # static nodeIDNum, increased everytime an algorithm is created
    nodeIDNum = 0;

    def __init__(self, descriptionfile):
        GeoAlgorithm.__init__(self)
        self.multipleRasterInput = False
        self.descriptionFile = descriptionfile
        self.defineCharacteristicsFromFile()
        self.nodeID = ""+self.operator+"_"+str(GPFAlgorithm.nodeIDNum)
        GPFAlgorithm.nodeIDNum +=1
        self.sourceFiles = ""
        self.previousAlgInGraph = None
        
    def helpFile(self, key):
        folder = GPFUtils.gpfDocPath(key)
        if str(folder).strip() != "":
            helpfile = os.path.join( str(folder), self.operator + ".html" )
            return helpfile
        return None
    
    # BEAM parameters dialog is the same as normal parameters dialog except
    # it has a button next to raster inputs to show band names
    # For now NEST uses the same dialog, maybe later that might have to change
    # if BEAM can't read band name from NEST images.
    def getCustomParametersDialog(self):
        return BEAMParametersDialog(self)
    
    def defineCharacteristicsFromFile(self):
        lines = open(self.descriptionFile)
        line = lines.readline().strip("\n").strip()
        self.operator = line
        line = lines.readline().strip("\n").strip()
        self.description = line
        line = lines.readline().strip("\n").strip()
        self.name = line
        line = lines.readline().strip("\n").strip()
        self.group = line
        while line != "":
            try:
                line = line.strip("\n").strip()
                if line.startswith("Parameter"):
                    param = ParameterFactory.getFromString(line)
                    self.addParameter(param)
                elif line.startswith("*Parameter"):
                    param = ParameterFactory.getFromString(line[1:])
                    param.isAdvanced = True
                    self.addParameter(param)
                else:
                    self.addOutput(OutputFactory.getFromString(line))
                line = lines.readline().strip("\n").strip()
            except Exception,e:
                SextanteLog.addToLog(SextanteLog.LOG_ERROR, "Could not open GPF algorithm: " + self.descriptionFile + "\n" + line)
                raise e
        lines.close()
    
    def addGPFNode(self, graph):
        
        # if there are previous nodes that should be added to the graph, recursively go backwards and add them
        if self.previousAlgInGraph != None:
            self.previousAlgInGraph.addGPFNode(graph)

        # now create and add the current node
        node = Element("node", {"id":self.nodeID})
        operator = SubElement(node, "operator")
        operator.text = self.operator
        
        # sources are added in the parameters loop below
        sources = SubElement(node, "sources")
        
        parametersNode = SubElement(node, "parameters")
        
        for param in self.parameters:
            # ignore parameters which should have no value unless set by user 
            if param.value == None or param.value == GPFAlgorithm.NOVALUEINT or param.value == GPFAlgorithm.NOVALUEDOUBLE:
                continue
            else:
                # add a source product
                if isinstance(param, ParameterRaster) and operator.text != "Read":
                    # if the source is a file, then add an external "source product" file
                    if os.path.isfile(param.value):
                        # check if the file should be added individually or through the
                        # ProductSet-Reader used sometimes by NEST
                        match = re.match("^\d*ProductSet-Reader>(.*)",param.name)
                        if match:
                            paramName = match.group(1)
                            productSetReaderNodeId = self.addProductSetReaderNode(graph, param.value)
                            if sources.find(paramName) == None:
                                source = SubElement(sources, paramName)
                                source.set("refid",productSetReaderNodeId)
                        else:
                            source = SubElement(sources, param.name)
                            source.text = "${"+param.name+"}"
                            self.sourceFiles = self.sourceFiles +"".join("-S"+param.name+"=\"" + param.value + "\" ")
                    # else assume its a reference to a previous node and add a "source" element
                    else:
                        source = SubElement(sources, param.name)
                        source.text = param.value   
                # add parameters
                else:
                    # Set the name of the parameter
                    # First check if there are nested tags
                    tagList = param.name.split(">")
                    parentElement = parametersNode
                    parameter = None
                    for tag in tagList:
                        # if this is the last tag or there are no nested tags create the parameter element
                        if tag == tagList[-1]:
                            # special treatment for geoRegionExtent parameter in Subset operator
                            if tag == "geoRegionExtent":
                                tag = "geoRegion"
                            # there can be only one parameter element in each parent element 
                            if len(parentElement.findall(tag)) > 0:
                                parameter = parentElement.findall(tag)[0]
                            else:
                                parameter = SubElement(parentElement, tag)
                        # "!" means that a new element in the graph should be created as child of the parent element and set as a parent    
                        elif tag.startswith("!"):
                            parentElement = SubElement(parentElement, tag[1:])
                        # otherwise just find the last element with required name and set it as parent of the parameter element
                        # or create a new one if it can't be found    
                        else:
                            if len(parentElement.findall(tag)) > 0:
                                parentElement = (parentElement.findall(tag))[-1]
                            else:
                                parentElement = SubElement(parentElement, tag)
                    
                    # Set the value of the parameter    
                    if isinstance(param, ParameterBoolean):
                        if param.value:
                            parameter.text = "True"
                        else:
                            parameter.text = "False"
                    elif isinstance(param, ParameterSelection):
                        idx = int(param.value)
                        parameter.text = str(param.options[idx])
                    # create at WKT polygon from the extent values, used in Subset Operator
                    elif isinstance(param, ParameterExtent):
                        values = param.value.split(",")
                        parameter.text = "POLYGON(("
                        parameter.text += values[0] + ' ' + values[2] +", "
                        parameter.text += values[0] + ' ' + values[3] +", "
                        parameter.text += values[1] + ' ' + values[3] +", "
                        parameter.text += values[1] + ' ' + values[2] +", "
                        parameter.text += values[0] + ' ' + values[2] +"))"
                    else:          
                        parameter.text = str(param.value)
        
        graph.append(node)
        return graph
        
    def addProductSetReaderNode(self, graph, filename):
        nodeID = self.nodeID+"_ProductSet-Reader"
        node = graph.find(".//*[@id='"+nodeID+"']")
        
        # add ProductSet-Reader node if it doesn't exist yet   
        if node == None:
            node = SubElement(graph, "node", {"id":nodeID})
            SubElement(node, "sources")
            operator = SubElement(node, "operator")
            operator.text = "ProductSet-Reader"
            # add the file list
            parametersNode = SubElement(node, "parameters")
            parameter = SubElement(parametersNode, "fileList")
            parameter.text=filename
        # otherwise append filename to the node's fileList
        else:
            parameter = node.find(".//fileList")
            parameter.text +=","+filename
        return nodeID
          
    def addWriteNode(self, graph):
        # add write node
        node = SubElement(graph, "node", {"id":self.nodeID+"_write"})
        operator = SubElement(node, "operator")
        operator.text = "Write"
        
        # add source
        sources = SubElement(node, "sources")
        source = SubElement(sources, "source")
        source.text = self.nodeID
    
        # add some options
        parametersNode = SubElement(node, "parameters")
        parameter = SubElement(parametersNode, "clearCacheAfterRowWrite")
        parameter.text = "False"
        parameter = SubElement(parametersNode, "deleteOutputOnFailure")
        parameter.text = "True"
        parameter = SubElement(parametersNode, "writeEntireTileRows")
        parameter.text = "True"
        parameter = SubElement(parametersNode, "formatName")
        parameter.text = "GeoTIFF"
        parameter = SubElement(parametersNode, "file")
        parameter.text = str((self.outputs[0]).value)
        
        return graph
    
    def processAlgorithm(self, key, progress):
        # create a GFP for execution with BEAM's GPT
        graph = Element("graph", {'id':self.operator+'_gpf'})
        version = SubElement(graph, "version")
        version.text = "1.0"
        
        # add node with this algorithm's operator
        graph = self.addGPFNode(graph)
        # For now use command line option (in GPFUtils) to write output, not sure it this matters or not
        #graph = self.addWriteNode(graph)
        
        # log the GPF 
        loglines = []
        loglines.append("GPF Graph")
        loglines.append(tostring(graph))
        loglines.append(self.sourceFiles)
        SextanteLog.addToLog(SextanteLog.LOG_INFO, loglines)
        
        # Execute the GPF
        # !!! should check that there is at least one output        
        GPFUtils.executeGpf(key, tostring(graph), (self.outputs[0]).value, self.sourceFiles, progress)
        
    def commandLineName(self):
        return self.provider.getName().lower().replace(" ", "") + ":" + self.operator.lower().replace("-","")
                