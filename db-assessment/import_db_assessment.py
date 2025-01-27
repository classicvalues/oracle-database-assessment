# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Basic python built-in libraries to enable read, write and manipulate files in the OS
import os
import glob
import sys

# Manages command line flags and arguments
import argparse

# Big Query Library Used to Import CSV files
from google.cloud import bigquery
from google.api_core.exceptions import Conflict

client = None # Declare this at the top after import statements

# Setting client info for Google APIs
import set_client_info

# Importing Optimus Prime Version
import version

# Information for analytics and tool improvement
__version__= version.__version__

# Messages handling
import logging
logging.getLogger().setLevel(level=logging.INFO)




def get_bigqueryClient():
    global client
    if not client:
        client = bigquery.Client(client_info=set_client_info.get_http_client_info())
    return client

def getVersion():

    return __version__

def consolidate_logs(args):

    tableSchemas = getBQJobConfig()
    file_counter = 0

    # For all expected tables we will look for related OS files. So, we will process all files related to a given expected tableName, then move to the next
    for tablename in tableSchemas:

        table_csvfiles = os.path.join(args.filelocation, 'opdb*', tablename, '*.log')
        consolidated_filepath = os.path.join(args.filelocation, 'opalldb__', tablename, '__consolidate.log')

        # Remove file if exists already for given table
        if os.path.exists(consolidated_filepath):
            print('The file {} already exists. It is going to be overwritten.'.format(consolidated_filepath))
            os.remove(consolidated_filepath)

        file_counter += 1
        table_file_counter = 0  # Counter for number of files per table

        for file_name in getAllFilesByPattern(table_csvfiles):

            if getAllFilesByPattern(file_name, '__', 1):

                table_file_counter += 1
                # Skip headers starting second file
                start_line = 2 if table_file_counter > 1 else 0

                with open(consolidated_filepath, 'a') as target_file:
                    
                    with open(file_name, 'r') as source_file:
                        
                        for line in source_file.readlines()[start_line:]:
                            target_file.write(line)
            else:
                raise Exception("<<appropriate error messsage>>")
                

    logging.info('The total files consolidated are %s. \nAll files are located in %s', file_counter, args.fileslocation)

    return True

def consolidateLos(args):
# This function intents to consolidate the collected files into a single large file to facilidate importing the data to Big Query

    # Creating Hash Table with all expected tableName schemas to be imported
    tableSchemas = {}
    tableSchemas = getBQJobConfig()

    # Counting all processed files
    fileCounter = 0

    # For all expected tables we will look for related OS files. So, we will process all files related to a given expected tableName, then move to the next
    for tableName in tableSchemas:

        fileCounter = fileCounter + 1

        # Using the expected tableName to look for files in the OS in the directory passed in -fileslocation (default dbResults)
        csvFilesLocationPattern = str(getattr(args,'fileslocation')) + '/opdb*' + str(tableName) + '*.log'

        # Generating a list with all found OS filenames
        fileList = getAllFilesByPattern(csvFilesLocationPattern)

        # To control how many files are being processed and identify the first processed file since it needs to bring the headers
        fileTableCounter = 0

        # Processing one file at a time for the expected tableName
        for fileName in fileList:

            # File Counter
            fileTableCounter = fileTableCounter + 1

            # Final table name from the CSV file names
            tableName = getObjNameFromFiles(fileName,'__',1)

            # Filename to be used to name consolidated file
            targetFileNameConsolidated = str(getattr(args,'fileslocation')) + '/opalldb__' + str(tableName) + '__consolidate.log'

            # Checks if file already exists in the first matching file found because the other files need to append to existent one.
            if fileTableCounter == 1:

                # If already exists delete the file
                if os.path.exists(targetFileNameConsolidated):
                    
                    print('The file {} already exists. It is going to be overwritten.'.format(targetFileNameConsolidated))
                    os.remove(targetFileNameConsolidated)

            # This is the file that will be used to be consolidated
            fileConsolidated = open(targetFileNameConsolidated,'a')

            # This file was found in the OS. The content of this file will be merged/consolidated into fileConsolidated
            fileToBeConsolidated = open(fileName, 'r')

            # Breaking it down into lines because first two lines must be skipped for all of the files (expect first file merged)
            # Since those files are expected to be small (< 10k lines) no performance issue is expected
            linesToBeConsolidated = []
            linesToBeConsolidated = fileToBeConsolidated.readlines()

            # To control how many lines are being processed and identify the first processed lines since it needs to skip it eventually
            lineCounter = 0
            for line in linesToBeConsolidated:

                # Line counters to be used to skip unecessary lines
                lineCounter = lineCounter + 1

                # Not processing first lines due to expected CSV headers. Except for the first file.
                if lineCounter <= 2 and fileTableCounter > 1:
                    
                    continue
                
                # Writting up the line from linesToBeConsolidated into fileConsolidated
                fileConsolidated.write(line)


            # Closing file handle
            fileToBeConsolidated.close()

            # Closing file handle
            fileConsolidated.close()

    print ('\nThe total files consolidated are {}. \nAll files are located in {}'.format(str(fileCounter),str(getattr(args,'fileslocation'))))

    return True

def createOptimusPrimeViews(gcpProjectName,bqDataset):
# This function intents to create all views found in the opViews directory. The views creation must follow opViews/<filename> order

    print ('\nPreparing to create Optimus Prime SQL Views\n')
    
    # Store all files found in the OS
    fileList = []

    # Searching for all matching files in the default views location
    filePattern = 'opViews/optimus_createView*.sql'

    # List with all views to be created
    fileList = getAllFilesByPattern(filePattern)
    
    if len(fileList) == 0:
        print('\nWARNING: No views found to be created at expected location: {}. Please make sure you the location is correct.'.format(filePattern))
        # Returns False if cannot create views    
        return False
    
    else:

        client = bigquery.Client(client_info=set_client_info.get_http_client_info())

        # Sorting list to make sure the proper view creation
        fileList.sort()

        # Looping to iterate all view files found in the OS to be created. Also, to extract the proper view name out of them.
        for viewFileName in fileList:

            # Extracting the proper view name to be created in Big Query based out of OS view filename
            view_name = str(getObjNameFromFiles(viewFileName,'__',1)).replace('.sql','')

            print ('Preparing to process {} and create the view name {}'.format(viewFileName,view_name))

            
            if gcpProjectName is None:
                # In case projectname is not provided in the arguments
                view_id = str(client.project) + '.' + str(bqDataset) + '.' + view_name
            else:
                # If projectname is provided in the arguments
                view_id = str(gcpProjectName) + '.' + str(bqDataset) + '.' + view_name
            
            # Creating the JOB to create view in Big Query
            view = bigquery.Table(view_id)

            # Extracting the view text and replacing the string ${dataset} by the proper dataset
            with open(viewFileName, "r") as view_content:
                view.view_query = view_content.read().replace('${dataset}',str(bqDataset))

            try:
                # Make an API request to create the view.
                view = client.create_table(view)
                print("Created {}: {}".format(view.table_type,str(view.reference)))
                print("\n")
            except Conflict as error:
                print("View {} already exists.\n".format(str(view.reference)))


        return True 
    

def getAllFilesByPattern(filePattern):
# This function intends to get the name of all files in the OS and return a list of strings

    # Get all matching files and creates a list returning it   
    return glob.glob(filePattern)

def importAllCSVsToBQ(gcpProjectName,bqDataset,fileList,skipLeadingRows):
# This function receives a list of files to import to Big Query, then it calls importCSVToBQ to import table/file by table/file

    print ('\nPreparing to upload CSV files\n')

    # Creating Hash Table with all expected table schemas to be imported
    tableSchemas = {}
    tableSchemas = getBQJobConfig()

    # Getting the name of the target table_name to import the data based on the filename from OS
    for fileName in fileList:
        
        # Default Big Query Job Configurations for Optimus Prime CSV files
        autoDetect = 'True'

        # Final table name from the CSV file names
        tableName = getObjNameFromFiles(fileName,'__',1)

        print ('\nThe filename {} is being imported to Big Query.'.format(fileName))

        # Import the given CSV fileName into 
        importCSVToBQ(gcpProjectName,bqDataset,tableName,fileName,skipLeadingRows,autoDetect,tableSchemas)

    return True

def importCSVToBQ(gcpProjectName,bqDataset,tableName,fileName,skipLeadingRows,autoDetect,tableSchemas):
# This function will import the CSV file into the Big Query using the proper project.dataset.tablename
# A Big Query Job is created for it

    # Getting table schema
    try:
        schema = tableSchemas[tableName]
    except KeyError:
        # In case there is not expected table schema found in getBQJobConfig function
        print ('\nWARNING: The filename {} could not be imported to Big Query.'.format(fileName))
        print ('The table name {} cannot be imported because it does not have table schema in Optimus Prime configuration. So, it will be skipped.\n')
        return False

    # Construct a BigQuery client object.
    client = bigquery.Client(client_info=set_client_info.get_http_client_info())

    # Adding Project and Dataset based on arguments 
    # table_id to the ID of the table to create.
    if gcpProjectName is not None:
        table_id = str(gcpProjectName) + '.' + str(bqDataset) + '.' + str(tableName)
    
    # In case projectname was passed as argument. Then, it tries to get the default project for the [service] account being used
    else:
        table_id = str(client.project) + '.' + str(bqDataset) + '.' + str(tableName)

    # table schema
    schema = []

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        skip_leading_rows=skipLeadingRows,
        # The source format defaults to CSV, so the line below is optional.
        source_format=bigquery.SourceFormat.CSV,
    )

    with open(fileName, "rb") as source_file:
        load_job = client.load_table_from_file(source_file, table_id, job_config=job_config)

    load_job.result()  # Waits for the job to complete.

    destination_table = client.get_table(table_id)  # Make an API request.
    print("Loaded {} rows into: {}".format(destination_table.num_rows,destination_table.reference))
    print ('The filename {} is successfully imported to Big Query.\n'.format(fileName))

    # returns True if processing is successfully
    return True


def getTableRef(dataset,tableName,projectName):
    
    if projectName:
        return f"{projectName}.{dataset}.{tableName}"

    return  f"{client.project}.{dataset}.{tableName}"

def getObjNameFromFiles(fileName,splitterChar,pos):
    # This function returns a string based on a string splitted(Created a list) by a given character. Then, it returns the desired index position of the list.

    return fileName.split(splitterChar)[pos]

def getBQJobConfig():
# Stores in a hash table all table schema configuration
# If multi database version schema is needed in the future we can include a key for the Dbversion. 
# In future this is best implemented if coming from a configuration file like a JSON file
# For example: bqTablesJobConfig['dbsummary']['11g']... 

    bqTablesJobConfig = {}

    # TableName: dbsummary
    bqTablesJobConfig['dbsummary'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("dbid", "STRING"),
        bigquery.SchemaField("db_name", "STRING"),
        bigquery.SchemaField("cdb", "STRING"),
        bigquery.SchemaField("dbversion", "STRING"),
        bigquery.SchemaField("dbfullversion", "STRING"),
        bigquery.SchemaField("log_mode", "STRING"),
        bigquery.SchemaField("force_logging", "STRING"),
        bigquery.SchemaField("redo_gb_per_day", "STRING"),
        bigquery.SchemaField("rac_dbinstaces", "STRING"),
        bigquery.SchemaField("characterset", "STRING"),
        bigquery.SchemaField("platform_name", "STRING"),
        bigquery.SchemaField("startup_time", "STRING"),
        bigquery.SchemaField("user_schemas", "STRING"),
        bigquery.SchemaField("buffer_cache_mb", "STRING"),
        bigquery.SchemaField("shared_pool_mb", "STRING"),
        bigquery.SchemaField("total_pga_allocated_mb", "STRING"),
        bigquery.SchemaField("db_size_allocated_gb", "STRING"),
        bigquery.SchemaField("db_size_in_use_gb", "STRING"),
        bigquery.SchemaField("db_long_size_gb", "STRING"),
        bigquery.SchemaField("dg_database_role", "STRING"),
        bigquery.SchemaField("dg_protection_mode", "STRING"),
        bigquery.SchemaField("dg_protection_level", "STRING"),
    ]

    # TableName: dboverview
    bqTablesJobConfig['dboverview'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("metric", "STRING"),
        bigquery.SchemaField("value", "STRING"),
    ]

    # TableName: pdbsinfo
    bqTablesJobConfig['pdbsinfo'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("dbid", "STRING"),
        bigquery.SchemaField("pdb_id", "STRING"),
        bigquery.SchemaField("pdb_name", "STRING"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("logging", "STRING"),
    ]

    # TableName: pdbsopenmode
    bqTablesJobConfig['pdbsopenmode'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("open_mode", "STRING"),
        bigquery.SchemaField("total_gb", "STRING"),
    ]

    # TableName: dbinstances
    bqTablesJobConfig['dbinstances'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("inst_id", "STRING"),
        bigquery.SchemaField("instance_name", "STRING"),
        bigquery.SchemaField("host_name", "STRING"),
        bigquery.SchemaField("version", "STRING"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("database_status", "STRING"),
        bigquery.SchemaField("instance_role", "STRING"),
    ]

    # TableName: usedspacedetails
    bqTablesJobConfig['usedspacedetails'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("segment_type", "STRING"),
        bigquery.SchemaField("tablespace_name", "STRING"),
        bigquery.SchemaField("flash_cache", "STRING"),
        bigquery.SchemaField("inmemory", "STRING"),
        bigquery.SchemaField("in_con_id", "STRING"),
        bigquery.SchemaField("in_owner", "STRING"),
        bigquery.SchemaField("in_segment_type", "STRING"),
        bigquery.SchemaField("in_tablespace_name", "STRING"),
        bigquery.SchemaField("in_flash_cache", "STRING"),
        bigquery.SchemaField("in_inmemory", "STRING"),
        bigquery.SchemaField("size_gb", "STRING"),
    ]

    # TableName: compressbytable
    bqTablesJobConfig['compressbytable'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("number_tables", "STRING"),
        bigquery.SchemaField("table_gb", "STRING"),
        bigquery.SchemaField("number_parts", "STRING"),
        bigquery.SchemaField("part_gb", "STRING"),
        bigquery.SchemaField("number_subparts", "STRING"),
        bigquery.SchemaField("subpart_gb", "STRING"),
        bigquery.SchemaField("total_gb", "STRING"),
    ]

    # TableName: compressbytype
    bqTablesJobConfig['compressbytype'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("basic", "STRING"),
        bigquery.SchemaField("oltp", "STRING"),
        bigquery.SchemaField("query_low", "STRING"),
        bigquery.SchemaField("query_high", "STRING"),
        bigquery.SchemaField("archive_low", "STRING"),
        bigquery.SchemaField("archive_high", "STRING"),
        bigquery.SchemaField("total_gb", "STRING"),
    ]

    # TableName: spacebyownersegtype
    bqTablesJobConfig['spacebyownersegtype'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("segment_type", "STRING"),
        bigquery.SchemaField("total_gb", "STRING"),
    ]

    # TableName: spacebytablespace
    bqTablesJobConfig['spacebytablespace'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("tablespace_name", "STRING"),
        bigquery.SchemaField("extent_management", "STRING"),
        bigquery.SchemaField("allocation", "STRING"),
        bigquery.SchemaField("segment_space_manage", "STRING"),
        bigquery.SchemaField("est_gain_mb", "STRING"),
    ]

    # TableName: freespaces
    bqTablesJobConfig['freespaces'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("tablespace", "STRING"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("total_gb", "STRING"),
        bigquery.SchemaField("used_gb", "STRING"),
        bigquery.SchemaField("free_gb", "STRING"),
        bigquery.SchemaField("pct_used", "STRING"),
        bigquery.SchemaField("graph", "STRING"),
    ]

    # TableName: dblinks
    bqTablesJobConfig['dblinks'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("db_link", "STRING"),
        bigquery.SchemaField("username", "STRING"),
        bigquery.SchemaField("host", "STRING"),
        bigquery.SchemaField("created", "STRING"),
    ]

    # TableName: dbparameters
    bqTablesJobConfig['dbparameters'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("inst_id", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("value", "STRING"),
        bigquery.SchemaField("default_value", "STRING"),
        bigquery.SchemaField("isdefault_value", "STRING"),
    ]

    # TableName: dbfeatures
    bqTablesJobConfig['dbfeatures'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("current_usage", "STRING"),
        bigquery.SchemaField("detected_usage", "STRING"),
        bigquery.SchemaField("total_samples", "STRING"),
        bigquery.SchemaField("first_usage", "STRING"),
        bigquery.SchemaField("last_usage", "STRING"),
        bigquery.SchemaField("aux_count", "STRING"),
    ]

    # TableName: dbhwmarkstatistics
    bqTablesJobConfig['dbhwmarkstatistics'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("description", "STRING"),
        bigquery.SchemaField("highwater", "STRING"),
        bigquery.SchemaField("last_value", "STRING"),
    ]

    # TableName: cpucoresusage
    bqTablesJobConfig['cpucoresusage'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("dt", "STRING"),
        bigquery.SchemaField("cpu_count", "STRING"),
        bigquery.SchemaField("cpu_core_count", "STRING"),
        bigquery.SchemaField("cpu_socket_count", "STRING"),
    ]

    # TableName: dbobjects
    bqTablesJobConfig['dbobjects'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("objecttype", "STRING"),
        bigquery.SchemaField("editionable", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
        bigquery.SchemaField("in_con_id", "STRING"),
        bigquery.SchemaField("in_owner", "STRING"),
        bigquery.SchemaField("in_object_type", "STRING"),
        bigquery.SchemaField("in_editionable", "STRING"),
    ]

    # TableName: sourcecode
    bqTablesJobConfig['sourcecode'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("type", "STRING"),
        bigquery.SchemaField("nr_lines", "STRING"),
        bigquery.SchemaField("qt_objs", "STRING"),
        bigquery.SchemaField("nr_lines_w_utl", "STRING"),
        bigquery.SchemaField("nr_lines_w_dbms", "STRING"),
        bigquery.SchemaField("nr_lines_w_exec_im", "STRING"),
        bigquery.SchemaField("nr_lines_w_dbms_sql", "STRING"),
        bigquery.SchemaField("nr_lines_w_dbms_utl", "STRING"),
        bigquery.SchemaField("nr_lines_total", "STRING"),
    ]

    # TableName: partsubparttypes
    bqTablesJobConfig['partsubparttypes'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("partition", "STRING"),
        bigquery.SchemaField("subpartition", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
    ]

    # TableName: indexestypes
    bqTablesJobConfig['indexestypes'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("index_type", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
    ]

    # TableName: datatypes
    bqTablesJobConfig['datatypes'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("data_type", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
    ]

    # TableName: tablesnopk
    bqTablesJobConfig['tablesnopk'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("pk", "STRING"),
        bigquery.SchemaField("uk", "STRING"),
        bigquery.SchemaField("ck", "STRING"),
        bigquery.SchemaField("ri", "STRING"),
        bigquery.SchemaField("vwck", "STRING"),
        bigquery.SchemaField("vmro", "STRING"),
        bigquery.SchemaField("hashexpr", "STRING"),
        bigquery.SchemaField("suplog", "STRING"),
        bigquery.SchemaField("num_tables", "STRING"),
        bigquery.SchemaField("total_cons", "STRING"),
    ]

    # TableName: systemstats
    bqTablesJobConfig['systemstats'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("stat_type", "STRING"),
        bigquery.SchemaField("stat_name", "STRING"),
        bigquery.SchemaField("value1", "STRING"),
        bigquery.SchemaField("value2", "STRING"),
    ]

    # TableName: patchlevel
    bqTablesJobConfig['patchlevel'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("time", "STRING"),
        bigquery.SchemaField("action", "STRING"),
        bigquery.SchemaField("namespace", "STRING"),
        bigquery.SchemaField("version", "STRING"),
        bigquery.SchemaField("id", "STRING"),
        bigquery.SchemaField("comments", "STRING"),
    ]

    # TableName: awrhistsysmetrichist
    bqTablesJobConfig['awrhistsysmetrichist'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("dbid", "STRING"),
        bigquery.SchemaField("instance_number", "STRING"),
        bigquery.SchemaField("hour", "STRING"),
        bigquery.SchemaField("metric_name", "STRING"),
        bigquery.SchemaField("metric_unit", "STRING"),
        bigquery.SchemaField("avg_value", "STRING"),
        bigquery.SchemaField("mode_value", "STRING"),
        bigquery.SchemaField("median_value", "STRING"),
        bigquery.SchemaField("min_value", "STRING"),
        bigquery.SchemaField("max_value", "STRING"),
        bigquery.SchemaField("sum_value", "STRING"),
        bigquery.SchemaField("perc50", "STRING"),
        bigquery.SchemaField("perc75", "STRING"),
        bigquery.SchemaField("perc90", "STRING"),
        bigquery.SchemaField("perc95", "STRING"),
        bigquery.SchemaField("perc100", "STRING"),
    ]

    # TableName: awrhistsystimemodel
    bqTablesJobConfig['awrhistsystimemodel'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("total_awr_secs", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("dbid", "STRING"),
        bigquery.SchemaField("instance_number", "STRING"),
        bigquery.SchemaField("hour", "STRING"),
        bigquery.SchemaField("stat_name", "STRING"),
        bigquery.SchemaField("hour_total_secs", "STRING"),
        bigquery.SchemaField("avg_value", "STRING"),
        bigquery.SchemaField("mode_value", "STRING"),
        bigquery.SchemaField("median_value", "STRING"),
        bigquery.SchemaField("perc50", "STRING"),
        bigquery.SchemaField("perc75", "STRING"),
        bigquery.SchemaField("perc90", "STRING"),
        bigquery.SchemaField("perc95", "STRING"),
        bigquery.SchemaField("perc100", "STRING"),
        bigquery.SchemaField("min_value", "STRING"),
        bigquery.SchemaField("max_value", "STRING"),
        bigquery.SchemaField("sum_value", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
    ]

    # TableName: awrhistosstat
    bqTablesJobConfig['awrhistosstat'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("total_awr_secs", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("dbid", "STRING"),
        bigquery.SchemaField("instance_number", "STRING"),
        bigquery.SchemaField("hour", "STRING"),
        bigquery.SchemaField("stat_name", "STRING"),
        bigquery.SchemaField("hour_total_secs", "STRING"),
        bigquery.SchemaField("avg_value", "STRING"),
        bigquery.SchemaField("mode_value", "STRING"),
        bigquery.SchemaField("median_value", "STRING"),
        bigquery.SchemaField("perc50", "STRING"),
        bigquery.SchemaField("perc75", "STRING"),
        bigquery.SchemaField("perc90", "STRING"),
        bigquery.SchemaField("perc95", "STRING"),
        bigquery.SchemaField("perc100", "STRING"),
        bigquery.SchemaField("min_value", "STRING"),
        bigquery.SchemaField("max_value", "STRING"),
        bigquery.SchemaField("sum_value", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
    ]

    # TableName: awrhistcmdtypes
    bqTablesJobConfig['awrhistcmdtypes'] = [
        bigquery.SchemaField("pkey", "STRING"),
        bigquery.SchemaField("hour", "STRING"),
        bigquery.SchemaField("command_type", "STRING"),
        bigquery.SchemaField("coun", "STRING"),
        bigquery.SchemaField("avg_buffer_gets", "STRING"),
        bigquery.SchemaField("avg_elapsed_time", "STRING"),
        bigquery.SchemaField("avg_rows_processed", "STRING"),
        bigquery.SchemaField("avg_executions", "STRING"),
        bigquery.SchemaField("avg_cpu_time", "STRING"),
        bigquery.SchemaField("avg_iowait", "STRING"),
        bigquery.SchemaField("avg_clwait", "STRING"),
        bigquery.SchemaField("avg_apwait", "STRING"),
        bigquery.SchemaField("avg_ccwait", "STRING"),
        bigquery.SchemaField("avg_plsexec_time", "STRING"),
    ]

    # TableName: optimusconfig_bms_machinesizes
    bqTablesJobConfig['optimusconfig_bms_machinesizes'] = [
        bigquery.SchemaField("cores", "STRING"),
        bigquery.SchemaField("ram_gb", "STRING"),
        bigquery.SchemaField("machine_size", "STRING"),
        bigquery.SchemaField("machine_size_short", "STRING"),
        bigquery.SchemaField("processor", "STRING"),
        bigquery.SchemaField("est_price", "STRING"),
    ]

    # TableName: optimusconfig_network_to_gcp
    bqTablesJobConfig['optimusconfig_network_to_gcp'] = [
        bigquery.SchemaField("network_to_gcp", "STRING"),
        bigquery.SchemaField("gbytes_per_sec", "STRING"),
        bigquery.SchemaField("mbytes_per_sec", "STRING"),
    ]

    # TableName: alertlog
    bqTablesJobConfig['alertlog2'] = [
        bigquery.SchemaField("message_time", "STRING"),
        bigquery.SchemaField("message_text", "STRING"),
        bigquery.SchemaField("host_id", "STRING"),
        bigquery.SchemaField("con_id", "STRING"),
        bigquery.SchemaField("component_id", "STRING"),
        bigquery.SchemaField("message_type", "STRING"),
        bigquery.SchemaField("message_level", "STRING"),
        bigquery.SchemaField("message_id", "STRING"),
        bigquery.SchemaField("message_group", "STRING"),
        bigquery.SchemaField("container_name", "STRING"),
    ]

    # Returns hash table with all expected table schemas
    return bqTablesJobConfig


def createDataSet(datasetName,gcpProjectName):
# Always try to create the dataset

    # Construct a BigQuery client object.
    client = bigquery.Client(client_info=set_client_info.get_http_client_info())

    # Set dataset_id=datasetName to the ID of the dataset to create.
    if gcpProjectName is None:
        # In case the user did NOT pass the project name in the arguments
        dataset_id = "{}.{}".format(client.project,datasetName)
    else:
        # In case tge use DID pass the project name in the arguments
        dataset_id = "{}.{}".format(gcpProjectName,datasetName)

    # Construct a full Dataset object to send to the API.
    dataset = bigquery.Dataset(dataset_id)

    # TODO(developer): Specify the geographic location where the dataset should reside.
    dataset.location =  client.location

    # Send the dataset to the API for creation, with an explicit timeout.
    # Raises google.api_core.exceptions.Conflict if the Dataset already
    # exists within the project.
    try:
        dataset = client.create_dataset(dataset)  # Make an API request.
        print("Created dataset {}.{}".format(client.project, dataset.dataset_id))
        
    except Conflict as error:
        # If dataset already exists
        print('Dataset {} already exists.'.format(dataset_id))
    

def runMain(args):
# Main function

    # Pre-Tasks before trying to import any data

    if getattr(args,'consolidatelogs'):

        # It is True if no fatal errors were found
        resConsolidation = consolidateLos(args)
    
    # For all cases in which those attributes are <> None it means the user wants to import data to Big Query
    # No need to further messaging for mandatory options because this is being done in argumentsParser function
    if getattr(args,'dataset') is not None and getattr(args,'optimuscollectionid') is not None:

        # STEP 1: Import customer database assessment data

        # Optimus Prime Search Pattern to find the target CSV files to be processed
        # The default location will be dbResults if not overwritten by the argument -fileslocation
        csvFilesLocationPattern = str(getattr(args,'fileslocation')) + '/*' + str(getattr(args,'optimuscollectionid')).replace(' ','') + '.log'

        # Getting a list of files from OS based on the pattern provided
        # This is the default directory to have all customer database results from oracle_db_assessment.sql
        fileList = getAllFilesByPattern(csvFilesLocationPattern)

        # In case there is no matching file in the OS
        if len(fileList) == 0:
            sys.exit('\nERROR: There is not matching CSV file found to be processed using: {}\n'.format(csvFilesLocationPattern))

        # Import the CSV files into Big Query
        gcpProjectName = getattr(args,'projectname')
        bqDataset = str(getattr(args,'dataset'))
        
        # Create the dataset to import the CSV data
        createDataSet(bqDataset,gcpProjectName)

        # Import the CSV data found in the OS
        importAllCSVsToBQ(gcpProjectName,bqDataset,fileList,2)


        # STEP 2: Import Optimus Prime Configuration Files


        # Getting file pattern for find config files in the OS to be imported
        csvFilesLocationPattern = 'opConfig/*.csv'

        # Getting a list of files from OS based on the pattern provided
        fileList = getAllFilesByPattern(csvFilesLocationPattern)

        # Import all Optimus Prime CSV configutation
        importAllCSVsToBQ(gcpProjectName,bqDataset,fileList,1)


        # STEP 3: Create Optimus Prime Views


        # Create Optimus Prime Views
        createOptimusPrimeViews(gcpProjectName,bqDataset)

def argumentsParser():
# function to handle all arguments to be used in cli mode for this code and enforces mandatory options

    # Creating an argpaser object
    parser = argparse.ArgumentParser()

    # Name of dataset to be created and have the data imported
    parser.add_argument("-ds","-dataset", type=str, default=None, help="name of the Big Query dataset to import all CSV files. If do not exists it will be created if exists the data is appended")

    # GCP project name to be used with the dataset
    parser.add_argument("-pn","-projectname", type=str, default=None, help="name of the Google Cloud project name used for the Big Query dataset")

    # OS csv files location to be imported to Big Query
    parser.add_argument("-fl","-fileslocation", type=str, default='dbResults', help="optimus prime files location to be imported")

    # Optimus collection ID is the number in the final part of the generated CSV files. For example: dbResults/opdb_dbfeatures_ol79-orcl-db02.ORCLCDB.ORCLCDB.180603.log. Collection ID is: 180603
    parser.add_argument("-ocid","-optimuscollectionid", type=str, default=None, help="optimus prime collection id from CSV files OR 'consolidate' for consolidated logs")

    # Consolidates different collection IDs found in the OS (dbResults/*log) into a single CSV per file type. 
    # For example: dbResults has 52 files. Meaning, 2 collection IDs (each one has 26 different file types). 
    # After the consolidation it produces 26 *consolidatedlogs.log which would have data from both collection IDs 
    parser.add_argument("-cl", "--consolidatelogs", default=False, help="consolidate all CSV files opdb*log found in dbResults/ directory", action="store_true")

    # Increase logging output level
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")

    # Execute the parse_args() method. Variable args is a namespace type
    args = parser.parse_args()

    # If not using -cl flag
    if args.consolidatelogs == False:

        # In case there is not dataset parameter set or with valid content in the arguments
        if (args.dataset is None or args.dataset == ''):
            sys.exit('\nERROR: The parameter -dataset cannot be omitted and it must have a valid name.\n')
        
        # In case project name/project id is not provided
        elif args.projectname is None:
            print ('\nWARNING: Google Cloud project name not provided. Optimus Prime will try to get it automatically from Google Big Query API call.\n')

        # In case optimus collection id is omitted
        elif args.optimuscollectionid is None:
            sys.exit('\nERROR: The parameter -optimuscollectionid cannot be omitted. Please provide the collection id from CSV files.\n')

    # Returns a namespace object with all arguments and its values
    return args

if __name__ == '__main__':

    # Handling arguments
    args = argumentsParser()

    # Call main function
    runMain(args)
