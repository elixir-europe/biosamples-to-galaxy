# BioSamples to Galaxy
[Based on Galaxy Data Source Examples repo](https://github.com/erasche/galaxy-data_source-examples/tree/master/flask) and https://github.com/mdshw5/galaxy-json-data-source
Simple data source examples to help others building databases which should have Galaxy integration. There are two types of data sources, `sync` and `async`. 

# Synchronous Data Sources

For these data source types, simply requesting a specific URL will provide/generate the data on demand and return it to the requester. For example, providing access to a static file.

Running the example:

1. Install `sync.xml` into your Galaxy toolbox
2. `pip install flask`
3. `python sync.py`
4. Use the tool in Galaxy

# Use Case for BioSamples
Given a publication with an Array Express ID: 
- how can I find other samples that are part of this experiment (e.g. BioSamples Groups)
- how can I get any other data that BioSamples knows for this sample and those in the group

