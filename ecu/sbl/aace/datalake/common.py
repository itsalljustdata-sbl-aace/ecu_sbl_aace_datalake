#!/usr/bin/env python
# coding: utf-8


__all__ : list = [
                  "addIndexCol",
                  "aliasColumns",
                  "are_strings_similar",
                  "castColumns",
                  "castColumnsToInt",
                  "cleanString",
                  "createExtraRow",
                  "custom_initcap",
                  "dfShape",
                  "Display",
                  "dropTable",
                  "escapeName",
                  "extract_actual_error",
                  "firstCharIsNumeric",
                  "fixDodgyAssessLevel",
                  "fixDodgyStatuses",
                  "fixDodgyThing",
                  "fixUpName",
                  "garbageCLO",
                  "getColsFromTable",
                  "getDistinctValsFromDataRowsInt",
                  "getJoinCondition",
                  "getLakehouseId",
                  "getSQL",
                  "getTables",
                  "getTempTableName",
                  "getWorkspace",
                  "insertColumnAndAlias",
                  "insertValueIntoList",
                  "lakehouse_properties",
                  "mountItUp",
                  "readTable",
                  "rename_columns_strip_prefix",
                  "rename_columns_with_prefix",
                  "replaceValueInList",
                  "selectTable",
                  "setDFTextWhenNull",
                  "setNullToZero",
                  "simpleMap",
                  "sparkSession",
                  "sqlQueryDataFrame",
                  "tablePath",
                  "writeTable",
                 ]  +   [
                        "spark", 
                        "APPNAME_DEFAULT",
                        ]



# Standard library imports
from pathlib import Path
import re
import difflib
from datetime import datetime
import pandas as pd
import time
from uuid import uuid4

# Third-party imports
from    delta.tables import DeltaTable
import  notebookutils
from    notebookutils import mssparkutils
from    pyspark.sql import DataFrame, SparkSession
from    pyspark.sql import functions as F
from    pyspark.sql import types as T
from    py4j.protocol import Py4JJavaError
import  sempy.fabric as fabric

# Local imports


APPNAME_DEFAULT : str = "ecu.sbl.aace.datalake.common"

spark : SparkSession

def  Display (thing):
    if isinstance(thing, (pd.DataFrame,DataFrame)):
        ...
    elif isinstance(thing, (dict,list)):
        if isinstance(thing,dict):
            thing = pd.DataFrame(list(thing.items()), columns=['Key', 'Value'])
        else:
            thing = pd.DataFrame(thing)
    else:
        print (thing)
        return
    display (thing)

def sparkSession (appName : str = None):
    if not appName:
        appName = APPNAME_DEFAULT
    global spark
    spark = (
            SparkSession
                .builder 
                .appName(APPNAME_DEFAULT) 
                .getOrCreate()
            )
    
sparkSession ()

def cleanString(input_string):
    # Use regex to replace all non-alphanumeric characters except underscores
    cleaned_string = re.sub(r'[^a-zA-Z0-9_]', '', input_string)
    return cleaned_string

def escapeName (name : str) -> str:
    if '.' in name:
        parts = name.split('.')
        return '.'.join([escapeName(p) for p in parts])
    elif '`' in name:
        return name
    elif ' ' in name or '-' in name:
        return f"`{name}`"
    else:
        return name

# # Data Lake functions

def firstCharIsNumeric(input_string : str) -> bool:
    return (input_string and isinstance(input_string,str) and input_string[0].isdigit())

# In[120]:
def getTempTableName (prefix : str = None) -> str:
    prefix = str(prefix).rstrip('_')
    if not prefix:
        prefix = 'tmp'
    tabName = cleanString('_'.join([prefix,
                                    datetime.now().strftime("%Y%m%d_%H%M%S"),
                                    str(uuid4()).replace('-','')
                                   ]
                                   )
                        )
    if firstCharIsNumeric(tabName):
        # First character of a table not allowed to be numeric (in Oracle at least!)
        tabName = f"_{tabName}"
            
    return tabName


# ## sqlQueryDataFrame

# In[121]:


def sqlQueryDataFrame (df : DataFrame | list[DataFrame], tempTableName : str | list[str], qrySql : str, printSQL : bool = False) -> DataFrame:
    if isinstance(tempTableName,str):
        tempTableName = [tempTableName,]
    if isinstance(df,DataFrame):
        df = [df,]
    assert  (   isinstance(df, list)
            and isinstance(tempTableName, list)
            and len(tempTableName) == len(df)
            and all(isinstance(d, DataFrame)    for d in df)
            and all(isinstance(t, str)          for t in tempTableName)
            )
    timings = []
    for theDF, theName in zip(df, tempTableName):
        start = time.perf_counter()
        theDF.createOrReplaceTempView(theName)
        timings.append ((theName,start,time.perf_counter()))

    if printSQL:
        print (qrySql if qrySql.strip()[:-1] == '\n' else f"{qrySql}\n")

    start = time.perf_counter()
    retval = spark.sql(qrySql)
    timings.append (('Query',start,time.perf_counter()))
    if printSQL:
        padLen = max([5,]+[len(theName) for theName in tempTableName])
        lines = []
        for theName, start, end in timings:
            duration_str = f"{(round(end-start,2)):.2f}s".rjust(6)
            lines.append(' : '.join([theName.ljust(padLen),duration_str]))
        lines.insert(0,'-'*max([len(l) for l in lines]))
        lines.append(lines[0])
        for l in lines:
            print(f"\t{l}")
    return retval


# ## getWorkspace

# In[122]:


def getWorkspace(workspaceId : str = None) ->  dict|list[dict]:
    if workspaceId:
        filterStr = f"id eq '{workspaceId}'"
    else:
        filterStr = None
    df = fabric.list_workspaces(filter = filterStr)
    ws = df.to_dict(orient='records')
    if len(ws) == 0:
        raise ValueError (f"Workspace not found {filterStr}")
    elif len(ws) == 1:
        return ws[0]
    return ws


# ## getLakehouseId

# In[123]:


def getLakehouseId (lakehouse_name : str, workspace_id : str = None) -> str:
    if not workspace_id:
        # Get the workspace ID
        workspace_id = fabric.get_workspace_id()

    thisLakehouse = mssparkutils.lakehouse.get(name = lakehouse_name, workspaceId = workspace_id)
    return thisLakehouse.get('id',None)


# ## mountItUp
#
# Mounts a LakeHouse

# In[124]:


def mountItUp (lh_properties : dict, mountName : str) -> dict:
    mount_name = f'/{mountName}'
    mssparkutils.fs.mount(lh_properties['abfsPath'], mount_name)
    mount_points = mssparkutils.fs.mounts()
    mp = next((mp for mp in mount_points if mp["mountPoint"] == mount_name))

    for k,v in mp.items():
        if k in lh_properties:
            print (k,v,lh_properties[k])
        else:
            lh_properties[k] = v
    if 'localPath' in lh_properties:
        lh_properties['localPath'] = Path(lh_properties['localPath'])
        for t in ['Tables','Files']:
            lh_properties[f'localPath{t}'] = lh_properties['localPath'].joinpath(t)
    return lh_properties


# ## lakehouse_properties
#
# Retrieves property dict for a LH

# In[125]:


def lakehouse_properties (
            lakehouse_name : str  = None,
            lakehouse_id : str  = None,
            workspace : str = None,
            mountName : str = None
            ) -> dict | list[dict]:
    """
    Sandeep Pawar | fabric.guru
    Returns properties of a lakehouse as a pandas df.
    Default workspace is used if workspace is None.

    """
    workspace = fabric.resolve_workspace_id(workspace) or fabric.get_workspace_id()

    if lakehouse_name:
        if isinstance(lakehouse_name,str):
            lhName = [lakehouse_name,]
        else:
            lhName = lakehouse_name
    else:
        lakehouses = mssparkutils.lakehouse.list(workspaceId = workspace)
        if lakehouse_id:
            try:
                lh = [l for l in lakehouses if l['id'] == lakehouse_id][0]
            except IndexError:
                raise FileNotFoundError(f"workspace.lakehouse '{workspace}'.'{lakehouse_id}'")
            lhName = [lh['displayName'],]
        else:
            lhName = [lh['displayName'] for lh in lakehouses]

    # Get the Lakehouse data
    data = [notebookutils.lakehouse.getWithProperties(name=n, workspaceId=workspace) for n in lhName]

    flattened = [
        {
        'lakehouse_id': d['id'],
        'type': d['type'],
        'lakehouse_name': d['displayName'],
        'description': d['description'],
        'workspaceId': d['workspaceId'],
        'oneLakeTablesPath': d['properties']['oneLakeTablesPath'],
        'oneLakeFilesPath': d['properties']['oneLakeFilesPath'],
        'abfsPath': d['properties']['abfsPath'],
        'sqlep_connectionString': d['properties']['sqlEndpointProperties']['connectionString'],
        'sqlep_id': d['properties']['sqlEndpointProperties']['id'],
        'sqlep_provisioningStatus': d['properties']['sqlEndpointProperties']['provisioningStatus']
    }
    for d in data]

    if lakehouse_name or lakehouse_id:
        # we called this for a specific LH
        if not mountName:
            return flattened[0]
        else:
            return mountItUp(
                            lh_properties   = flattened[0],
                            mountName       = mountName
                            )
    else:
        # we called this for all LH in workspace
        return flattened


# ## getSQL

# In[126]:


def getSQL (tableName: str, cols: list[str]|str, distinct: bool = False) -> str:
    if isinstance(cols,str):
        cols = [cols,]
    cols = [escapeName(c) for c in cols]
    joinSep = ",\n         "
    stm = f"SELECT {joinSep.join(cols)}\n FROM {escapeName(tableName)} "
    if distinct:
        stm += f" \nGROUP BY {joinSep.join(cols)}"
    return stm


# ## getColsFromTable
#
# Selects data from a table, optionally grouping by the columns selected to get a DISTINCT dataset

# In[127]:


def getColsFromTable (tableName: str, cols: list[str]|str,lh_properties: dict = None, distinct: bool = False) -> DataFrame:
    return selectTable(lh_properties = lh_properties, tableName = tableName, query = getSQL(tableName,cols,distinct))


# ## tablePath

# In[128]:


def tablePath (lh_properties: dict, tableName: str) -> str:
    tabPath = f"{lh_properties['source']}/Tables/{tableName}"
    return tabPath


# In[129]:


def extract_actual_error(py4j_error : Py4JJavaError|str):
    if isinstance(py4j_error,Py4JJavaError):
        py4j_error =str(py4j_error)
    # Split the error message by newline
    lines = py4j_error.split('\n')

    # Find the line that starts with 'Caused by:'
    for line in lines:
        if line.strip().startswith('Caused by:'):
            return line.strip()

    # If 'Caused by:' is not found, return the first line of the error
    return lines[0].strip()


# ## selectTable

# In[130]:


def selectTable(lh_properties: dict, tableName: str, query: str = None):

    try:
        # Register the table as a temporary view
        df = spark.read.format("delta").load(tablePath(lh_properties,tableName))
        tableName = getTempTableName(tableName)
        df.createOrReplaceTempView(tableName)
        if not query:
            query = f'SELECT t.* FROM {escapeName(tableName)} AS t'
        # Execute the spark
        result_df = spark.sql(query)
    except Py4JJavaError as e:
        raise Py4JJavaError(extract_actual_error(e))


    return result_df


# ## readTable

# In[131]:


def readTable(lh_properties: dict, tableName: str, columns: list|list[str] = "*", condition: str = ""):

    # Define the SQL query
    if not columns:
        columns = ['*',]
    elif isinstance(columns,str):
        columns = [columns,]

    columns = [c if c == '*' else escapeName(c) for c in columns]
    tableName = escapeName(tableName)
    query = f"SELECT {','.join(columns)} FROM {tableName}"
    if condition:
        query += f"WHERE {condition}"
    return selectTable (lh_properties = lh_properties,
                tableName = tableName)


# ## getTables

# In[132]:


def getTables(lh_properties : dict) -> list:
    # Assuming lh_properties contains a base path for the datalake
    if 'localPathTables' not in lh_properties:
        raise Exception ('Not mounted')
    tablesPath = lh_properties['localPathTables']
    theTables = [t.name for t in list(tablesPath.glob('*/'))]
    return theTables



# ## dropTable

# In[133]:


def dropTable(lh_properties: dict, tableName: str, spark: SparkSession = None):
    path = tablePath(lh_properties,tableName)
    # print(f"Dropping table at path: {path}")
    if not spark:
        spark = spark
    DeltaTable.forPath(spark, path).delete()


# ## writeTable

# In[134]:


def writeTable (lh_properties: dict, tableName : str, df : DataFrame, partitionBy : str|list[str] = None) -> dict:

    path = tablePath(lh_properties,tableName)
    writer = df.write
    if partitionBy:
        writer.partitionBy(partitionBy)
    writer.format("delta").mode("overwrite").option("overwriteSchema", "true").save(path)
    return dict (**dfShape(df),
                 path = path
                 )


# ## writeSilverTable

# In[135]:



# # Text / List manipulation

# ## are_strings_similar

# In[138]:


def are_strings_similar(str1, str2, threshold=0.6):
    """
    Compare two strings and return True if they are similar based on the given threshold.

    :param str1: First string to compare.
    :param str2: Second string to compare.
    :param threshold: Similarity threshold (default is 0.6).
    :return: True if strings are similar, False otherwise.
    """
    similarity = difflib.SequenceMatcher(None, str1, str2).ratio()
    return similarity >= threshold


# ## fixDodgyThing

# In[139]:


def fixDodgyThing (value : str, legit_values : list[str] | str = None) -> str:
    if isinstance(legit_values,str):
        legit_values = [legit_values,]
    if not value:
        value = 'None Supplied'
    elif not isinstance(value,str):
        value = str(value)
    value = value.title()
    if legit_values and value not in legit_values:
        for l in legit_values:
            if are_strings_similar(value,l):
                value = l
                break
    return value


# ## insertValueIntoList

# In[140]:


def insertValueIntoList (theList: list, oldVal: str, newVal: str) -> list:
    if oldVal not in theList:
        result = theList
        result.append(newVal)
    elif newVal in theList:
        result = theList
    else:
        result = []
        for item in theList:
            if item == oldVal:
                result.append(newVal)
            else:
                result.append(item)
        result.append(oldVal)
    return result


# ## replaceValueInList

# In[141]:


def replaceValueInList (theList : list, oldVal : str, newVal: str) -> list:
    return  [newVal if item == oldVal else item for item in theList]


# # Dataframe Manipulation

# ## UDF for calling in dataframe manipulation
#
# These are also "normal" functions (without the UDF wrapper) so can be called wherever else you like


# ### custom_initcap

# In[143]:


def custom_initcap(name : str) -> str:

    if not name:
        return None
    elif not isinstance(name,str):
        name = str(name)

    delimiters = [" ", "'", "-", "`", "/"]

    def split_string_by_delimiters(string, delimiters):
        # Create a regular expression pattern that matches any of the delimiters
        pattern = f"({'|'.join(map(re.escape, delimiters))})"
        # Split the string using the pattern and keep the delimiters
        return re.split(pattern, string)

    def is_mixed_case(s):
        has_upper = any(c.isupper() for c in s)
        has_lower = any(c.islower() for c in s)
        return has_upper and has_lower

    def output_as_lowercase(s):
        return s.lower() in ['de','of']

    def capitalize_parts(parts):
        return [part if part in delimiters or is_mixed_case(part) else part.lower() if output_as_lowercase(part) else part.capitalize() for part in parts]

    # Reassemble the string with the original delimiters
    def reassemble_string(parts):
        return ''.join(parts)

    return reassemble_string(capitalize_parts(split_string_by_delimiters(name, delimiters)))

# Register the function as a UDF
custom_initcap_udf = F.udf(custom_initcap, T.StringType())


# ### fixUpName

# In[144]:


def fixUpName (name : str) -> str:
    if not name:
        return name
    elif name.strip() == ',':
        return None
    elif not isinstance(name,str):
        name = str(name)
    name = custom_initcap(name)
    name = name.split('(',1)[0].strip()
    if ',' in name:
        name = reversed(name.split(','))
        name = ' '.join([n.strip() for n in name])
    return name

# Register the function as a UDF
fixUpName_udf = F.udf(fixUpName, T.StringType())


# ### garbageCLO

# In[145]:


def garbageCLO (thisCLO : str) -> bool:
    return (not thisCLO
         or not isinstance(thisCLO,str)
         or thisCLO.lower().strip() == 'n/a'
        )
garbageCLO_udf = F.udf(garbageCLO, T.BooleanType())


# ### fixDodgyStatuses

# In[146]:


def fixDodgyStatuses (status : str) -> str:
    return fixDodgyThing(status, ['Completed','Discontinued','Enrolled'])

# Register the function as a UDF
fixDodgyStatuses_udf = F.udf(fixDodgyStatuses, T.StringType())


# ### fixDodgyAssessLevel

# In[147]:


def fixDodgyAssessLevel (assessLevel : str) -> str:
    return fixDodgyThing(assessLevel, ['Consolidated','Demonstrated'])

# Register the function as a UDF
fixDodgyAssessLevel_udf = F.udf(fixDodgyAssessLevel, T.StringType())


# ## getDistinctValsFromDataRowsInt

# In[148]:


def getDistinctValsFromDataRowsInt (df : DataFrame, colNames : list[str]|str, rowCountCol:str =None, indexStart:int =0, suppressNullRawScore: bool = False):
    # Ensure colNames is a list
    if isinstance(colNames, str):
        colNames = [colNames,]

    # Filter rows where RawScore is not null if suppressNullRawScore is True
    if suppressNullRawScore:
        df = df.filter(F.col("RawScore").isNotNull())

    # Group by colNames and optionally add rowCountCol
    if rowCountCol:
        df = df.groupBy(colNames).agg({rowCountCol: "count"}).withColumnRenamed(f"count({rowCountCol})", rowCountCol)
    else:
        df = df.groupBy(colNames).count().drop("count")

    # Sort the DataFrame by colNames
    df = df.orderBy([F.col(c).asc() for c in colNames])

    # add the index column
    indexCol = "index" + ("".join(colNames)).replace('_','')
    df = addIndexCol (df= df, indexColName = indexCol,indexStart = indexStart, newColPos = 0)

    return df


# ## setDFTextWhenNull

# In[149]:


def setDFTextWhenNull(df: DataFrame, column_name: str, nullVal: str) -> DataFrame:
    df = df.withColumn(column_name, F.when(F.col(column_name).isNull(), nullVal).otherwise(F.col(column_name)))
    return df


# ## setNullToZero

# In[150]:


def setNullToZero (df : DataFrame, column_names : str|list[str]) -> DataFrame:
    if isinstance(column_names,str):
        column_names = [column_names,]
    for c in [c for c in column_names if c in df.columns]:
        df = df.withColumn(c,
                            F.when(F.col(c).isNull(), 0)
                            .otherwise(F.col(c)))
    return df


# ## createExtraRow

# In[151]:


def createExtraRow (df : DataFrame, *args):
    # Create a list with the first passed values and fill the rest with None
    new_row_data = list(args) + ([None] * (len(df.schema.fields) - len(args)))

    # Create the Row object with this list
    new_row = T.Row(*new_row_data)

    # Convert the Row object to a DataFrame with the same schema as SILVER_CLO
    new_row_df = setNullToZero(spark.createDataFrame([new_row], schema=df.schema),'isActualMetadata')

    df = df.union(new_row_df).orderBy([df.schema.fields[0].name])

    return df


# ## rename_columns_with_prefix

# In[152]:


def rename_columns_with_prefix(df, prefix):
    for col_name in df.columns:
        df = df.withColumnRenamed(col_name, f"{prefix}_{col_name}")
    return df


# ## rename_columns_split_prefix

# In[153]:


def rename_columns_strip_prefix(df, prefix : str | list):
    if isinstance(prefix,str):
        prefix = [prefix,]
    for p in prefix:
        for col_name in df.columns:
            if col_name.startswith(p):
                col_name_new = col_name[len(p):].lstrip('_')
                if col_name_new:
                    #print (f"{col_name} => {col_name_new}")
                    df = df.withColumnRenamed(col_name, col_name_new)
    return df


# ## castColumns

# In[154]:


def castColumns (df : DataFrame, castCols : list[str]|str, cast : str) -> DataFrame:
    if isinstance(castCols,str):
        castCols = [castCols,]
    def raise_exception(column_name, cast_type):
        raise ValueError(f"Failed to cast column '{column_name}' to {cast_type}")
    for c in castCols:
        # Rename the original column
        origName = f"{c}_orig"
        if origName in df.columns:
            df = df.drop (origName)

        df = df.withColumnRenamed(c, origName)
        cols = df.columns
        cols.insert(cols.index(origName), c)

        # Perform the cast and create a new column with the original name
        df = df.withColumn(
            c,
            F.when(F.col(origName).isNull(), F.lit(None).cast(cast))
            .otherwise(
                F.when(F.col(origName).cast(cast).isNotNull(), F.col(origName).cast(cast))
                .otherwise(F.lit(None).cast(cast))
            )
        ).select(*cols)


        # Check if there are no rows where orig is not null and new column is null
        cnt = df.filter(F.col(origName).isNotNull() & F.col(c).isNull()).count()
        if cnt == 0:
            df = df.drop(origName)
        else:
            print (f"{c} : {cast} : {cnt} : Unable to cast all values")

    return df


# ## castColumnsToInt

# In[155]:


def castColumnsToInt (df : DataFrame, castCols : list[str]|str) -> DataFrame:
    return castColumns (df = df, castCols = castCols, cast = 'int')


# ## addIndexCol
#
# Adds a index column onto a DataFrame, with the value based on the index of the current row

# In[156]:


def addIndexCol (df : DataFrame, indexColName: str,indexStart: int = 0, newColPos : int = 0) -> DataFrame:
    if indexColName:
        columns = [c for c in df.columns if not c.upper() == indexColName.upper()]
        df = df.withColumn(indexColName, F.monotonically_increasing_id() + 1 + indexStart)
        if newColPos > len(columns):
            columns.append(indexColName)
        else:
            columns.insert(newColPos,indexColName)
        df = df.select(columns)
    return df


# ## dfShape

# In[158]:


def dfShape (df : DataFrame) -> dict:
    return dict (shape = (df.count(),len(df.columns)),
                 columns = df.columns,
                 )


# ## Join Wrappers

# ### getJoinCondition

# In[159]:


def getJoinCondition (factCol : str, mapCol : str = None) -> F.expr:
    if not mapCol:
        mapCol = factCol
    return F.expr(f"""
    (fact.{factCol} = map.{mapCol}
     OR (fact.{factCol} IS NULL AND map.{mapCol} IS NULL)
    )""")


# ### simpleMap

# In[160]:


def simpleMap (factDF : DataFrame, metadataDF : DataFrame, joinCol: str, joinType : str = "inner"):

    aliasedFact = factDF.alias('fact')
    indexCol : str = metadataDF.columns[0]
    theMap = metadataDF.select([indexCol,joinCol]).alias("map")
    factCols = aliasedFact.columns
    if joinCol not in factCols:
        if indexCol in factCols:
            print (f"{joinCol} not in factDF - already replaced by {indexCol}")
            return factDF
        else:
            raise Exception (f"{joinCol} not in factDF")
    elif indexCol in factCols:
        raise Exception (f"{indexCol} already in factDF. This shouldn't happen")
    else:
        before = factDF.count()

        join_condition = (F.col(f"map.{joinCol}") == F.col(f"fact.{joinCol}")) | (F.col(f"map.{joinCol}").isNull() & F.col(f"fact.{joinCol}").isNull())
        selectCols = insertColumnAndAlias(factCols,joinCol,indexCol,theMap.columns)
        aliasedFact = aliasedFact.join(
                                other   = theMap.hint("broadcast"),
                                on      = join_condition,
                                how     = joinType
                                ).select(selectCols)
        after = aliasedFact.count()
        if not before==after:
            print ("*"*80)
            print ("*"*80)
            print (f"{joinCol} : {before} - {after}")
            print ("*"*80)
            print ("*"*80)
            raise ValueError
        return aliasedFact


# ### aliasColumns

# In[161]:


def aliasColumns (selectCols : list[str], indexCol : str) -> list[str]:
    return [f'map.{c}' if c == indexCol else f"fact.{c}" for c in selectCols]


# ### insertColumnAndAlias

# In[162]:


def insertColumnAndAlias (columns : list[str], valColumn: str, indexColumn : str, mapColumns : list[str] = None) -> list[str]:
    cols = insertValueIntoList(theList = columns, oldVal = valColumn, newVal = indexColumn)
    # aliased = aliasColumns (selectCols = cols, indexCol = indexColumn)
    aliased = [f"fact.{c}" if c == valColumn else f"map.{c}" if c == indexColumn else c for c in cols]
    if mapColumns:
        aliasedMore = [f"fact.{c}" if '.' not in c and c in mapColumns else c for c in aliased]
        if not aliasedMore == aliased:
            print (aliasedMore)
            aliased = aliasedMore
    # print ([z for z in zip(cols,aliased)])c
    return aliased

