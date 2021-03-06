from flask import Flask, request, redirect, render_template, session, jsonify
app = Flask(__name__)
import urllib
import urlparse
import json, requests
import pandas as pd
from xml.etree import ElementTree as ET
import io

import logging

HEAD = "<html><head><title>Sync Galaxy Test</title></head><body>"
TAIL = "</body></html>"

class AE_sample :

    def __init__(self, newName):
        self.name = newName
        self.paired = False
        self.extension = '' # OF ENA DATA !!
        self.metadata = {}
        self.forward_ftp = None
        self.reverse_ftp = None
        self.AE_ftp = []

    def add_forward_ftp (self, uri):
        self.forward_ftp = uri

    def add_reverse_ftp (self, uri):
        self.reverse_ftp = uri
        self.paired =  True

    def add_AE_ftp (self, uri):
        self.AE_ftp.append(uri)

    def set_extension (self, ext):
        self.extension  =  ext

    def add_metadata (self, key, value):
        self.metadata[key] = value

    def __str__(self):
        mode = 'SE'
        if self.paired:
            mode = 'PE'
        files = []
        if self.forward_ftp:
            files.append(self.forward_ftp)
        if self.reverse_ftp:
            files.append(self.reverse_ftp)

        return "{name} ({mode})\n\t{file}\n".format(name = self.name, mode = mode, file = '\n\t'.join(files))

    def ena_json_item (self, uri, mode):
        item = {}
        item['url'] = uri
        item['name'] = "{sample} {mode}".format(sample=self.name, mode=mode)
        item['extension'] = self.extension
        item['metadata'] = self.metadata

        item['extra_data'] = [
            {
                "url" : uri,
                "path" : uri
            }
        ]
        return item

    def ae_json_item (self, uri):
        item = {}
        extension = uri.split('/')[-1].split('.')[-1]
        item['url'] = uri
        item['name'] = "{sample} ({filetype})".format(sample=self.name, filetype=extension)
        item['extension'] = extension
        item['metadata'] = self.metadata

        item['extra_data'] = [
            {
                "url" : uri,
                "path" : uri
            }
        ]
        return item

    def galaxy_json_items (self):
        items = []
        if self.forward_ftp:
            items.append(self.ena_json_item(self.forward_ftp, 'forward'))
            print "ENA ", self.forward_ftp
        if self.reverse_ftp:
            items.append(self.ena_json_item(self.reverse_ftp, 'reverse'))
            print "ENA ", self.reverse_ftp
        for ae in self.AE_ftp:
            items.append(self.ae_json_item(ae))
            print "AE  ", ae
        return items

def _get_fastq_from_ENA_RUN (ena_link, sample):
    files = []
    ena_sample_file = "{ena_link}&display=xml".format(ena_link=ena_link)
    ena_sample_content = requests.get(ena_sample_file).content
    #print(ena_content)
    ena_sample_root_element = ET.fromstring(ena_sample_content)
    ena_run = None
    for child in ena_sample_root_element.iter():
        if child.tag == 'SAMPLE_LINKS':
            for s in child.iter():
                if 'ERR' in s.text:
                    #print(s.text)
                    ena_run = s.text
        elif child.tag == 'SAMPLE_ATTRIBUTE':
            for s in child.iter():
                if s.tag == 'SAMPLE_ATTRIBUTE':
                    pass
                elif s.tag == 'TAG':
                    new_tag = s.text
                elif s.tag == 'VALUE':
                    new_value = s.text
                    if not 'ENA-' in new_tag:
                        sample.add_metadata(new_tag, new_value)
                        #print("%s : %s" % (new_tag, new_value))

                else:
                    print("UNEXPECTED TAG : %s" % s.tag)
    if ena_run:
        ena_run_file = "http://www.ebi.ac.uk/ena/data/warehouse/filereport?accession={ena_run}&result=read_run&fields=fastq_ftp".format(ena_run=ena_run)
        ena_run_content = requests.get(ena_run_file).content
        for line in ena_run_content.decode('utf-8').split():
            if 'ftp.sra.ebi.ac.uk/vol1/fastq/' in line:
                for uri in line.split(';'):
                    #print(uri)
                    files.append("ftp://{uri}".format(uri=uri))
    else:
        print("No RUN found")

    for fastq_uri in files:
        if '_1.fastq' in fastq_uri:
            sample.add_forward_ftp(fastq_uri)
        elif '_2.fastq' in fastq_uri:
            sample.add_reverse_ftp(fastq_uri)
        if not sample.extension:
            sample.set_extension(fastq_uri.split('/')[-1].split('.',1)[1])
        else :
            if sample.extension != fastq_uri.split('/')[-1].split('.',1)[1]:
                print("Forward and reverse different extension ?")

    return sample

def _get_data_from_AE(ae_link, sample):
    ae_id = ae_link.split('/')[-1]

    srdf_file = "http://www.ebi.ac.uk/arrayexpress/files/{acc}/{acc}.sdrf.txt".format(acc = ae_id)
    #print(srdf_file)
    AE_content = requests.get(srdf_file).content
    AE_table = pd.read_table(io.StringIO(AE_content.decode('utf-8')))
    AE_table = AE_table.loc[AE_table['Source Name'] == sample.name]

    numberOfDerivedFiles = 0
    checkNextColumn = True
    files = []
    while checkNextColumn:
        postfix = ''
        if numberOfDerivedFiles > 0:
            postfix = ".%d" %  numberOfDerivedFiles

        columnName = "Comment [Derived ArrayExpress FTP file]%s" % postfix
        if columnName in AE_table:
            #print("OK %s" % columnName)
            numberOfDerivedFiles += 1
            files.extend(AE_table.drop_duplicates(columnName)[columnName].values.tolist())
        else:
            #print("NOT %s" % columnName)
            checkNextColumn = False

    for f in files:
        sample.add_AE_ftp(f)

    return sample


@app.route("/search_input")
def search_input():
    """ 
    Take in a search term and return a list of Sample IDs and other metadata. 
    """
    bs_search = request.args.get('sample_ids', type=str)
    BIOSAMPLES_SEARCH = "http://www.ebi.ac.uk/biosamples/api/samples/search/findByText?text="+bs_search
    # print "** BSS: ", BIOSAMPLES_SEARCH
    all_sample_accessions = _get_samples(BIOSAMPLES_SEARCH)
    return jsonify(all_sample_accessions)


@app.route("/", methods=['GET', 'POST'])
def hello():
    print "hello() called..."
    print "Method call: ", request.method
    
    """Index page

    1. Upon choosing the datasource Galaxy performs a HTTP POST request to the
    external datasource's url (specified in the tool configuration file) and passes
    the parameter GALAXY_URL in this request. The value of this parameter contains
    the url where Galaxy will expect the response to be sent at some later time.
    The external site's responsibility is to keep track of this URL as long as the
    user navigates the external site.

    2. As the user navigates the external datasource, it behaves exactly as if
    it would if the request would have not originated from Galaxy
    """

    # Normally we would store this in their session data
    # gx_url = urllib.urlencode({'gx_url': request.args['GALAXY_URL']})
    # print "** gx_url: ", request.args['GALAXY_URL']
    # # for use with Flask Session
    # gx_url = request.args['GALAXY_URL']
    # session['gx_url'] = gx_url

    # However we aren't developing a big application, so we simply pass it in the URL
    # export_url = '/export/?' + gx_url
    # print "** EXPORT_URL", export_url

    # Test: Get list of Biosamples to display on demo page
    # resource_id = "E-MTAB-3173"
    # BIOSAMPLES_URL = "http://www.ebi.ac.uk/biosamples/api/samples/search/findByText?text=%22"+resource_id+"%22"
    # all_sample_accessions = _get_samples(BIOSAMPLES_URL)
    # print all_sample_accessions

    # Store list of samples as a Session variable
    # session['all_samples'] = all_sample_accessions
    # print "** Session - all samples accs: ", session['all_samples']


    # export_url is where the "fun" will happen.
    # return HEAD + "<h1>Galaxy Sync Data Source Test</h1>" + '<a href="' + export_url + '">Export Data</a>' + get_request_params() + TAIL

    # use template
    if request.method == 'GET':
        print "** gx_url: ", request.args['GALAXY_URL']
        # for use with Flask Session
        gx_url = request.args['GALAXY_URL']
        session['gx_url'] = gx_url
        return render_template('index.html')
    else:
        app.logger.info("** DATA POSTED")
        # app.logger.info(gx_url)
        sample_values = request.form.getlist('check')
        print "CB: ", sample_values
        # Store list of samples as a Session variable
        session['all_samples'] = sample_values
        print "** Session - all samples accs: ", session['all_samples']
        return export()


def get_request_params():
    app.logger.info("get_request_params() called")
    """Simply function to display request arguments as a table."""
    result = '<table border=1><thead><tr><th>Key</th><th>Value</th></tr><tbody>'
    for key in request.args:
        result += '<tr><td>%s</td><td>%s</td></tr>' % (key, request.args[key])
    return result + '</tbody></table>'


@app.route("/get_data_for_galaxy/")
def get_data():
    response = []
    for key in request.args:
        print "RK: ", request.args[key].split(',')
        # response.append('%s\t%s' % (key, request.args[key]))
        # response.append('%s' % request.args[key])
        response = request.args[key].split(',')
    print "Formatted Response: ", response

    all_sample_accessions = response

    # Assume that a list of BioSample Accessions is needed
    # resource_id = "E-MTAB-3173"
    # BIOSAMPLES_URL = "http://www.ebi.ac.uk/biosamples/api/samples/search/findByText?text=%22"+resource_id+"%22"
    # all_sample_accessions = _get_samples(BIOSAMPLES_URL)

    biosamples_response = []

    sample_count = 0
    for acc in all_sample_accessions:
        sample_count += 1

        if sample_count < 2:
            print "** Sample Accession for Data Export: ", acc
            # create new sample
            biosample_details = "http://www.ebi.ac.uk/biosamples/api/samples/{acc}".format(acc=acc)
            biosample_details_content = requests.get(biosample_details).content
            biosample_details_json = json.loads(biosample_details_content.decode('utf-8'))

            name = acc
            # if array express data is present I assume the name in BioSamples json
            # can be used to filter relevant data from AE srdf
            # name is not always present in the json
            if 'name' in biosample_details_json:
                name = biosample_details_json['name'].replace('source ', '')
                print(name)
            sample = AE_sample(name)

            # get external links from BioSamples and parse out the ENA sample name
            # assumptions:
            # * url contains ERS for ENA
            # * url contains E-MTAB for ArrayExpress
            # * the last link is taken
            biosample_externalLinks = "http://www.ebi.ac.uk/biosamples/api/samplesrelations/{acc}/externalLinks".format(acc=acc)
            biosample_externalLinks_content = requests.get(biosample_externalLinks).content

            biosample_externalLinks_json = json.loads(biosample_externalLinks_content.decode('utf-8'))
            ena_link = None
            ae_link = None
            for link in biosample_externalLinks_json['_embedded']['externallinksrelations']:
                if 'ERS' in link['url']:
                    ena_link = link['url']
                if 'E-MTAB' in link['url']:
                    ae_link = link['url']

            # if no link is found, skip
            if ena_link:
                sample = _get_fastq_from_ENA_RUN(ena_link, sample)
            else :
                print("No ENA link found")

            if ae_link:
                # assumes there is a sample already
                sample = _get_data_from_AE(ae_link, sample)
            else :
                print("No ArrayExpress link found")

            print(sample)
            biosamples_response.extend(sample.galaxy_json_items())

    # test file
    # biosamples_response = [{'url': 'http://www.ebi.ac.uk/arrayexpress/files/E-MTAB-4758/E-MTAB-4758.idf.txt', 'name': 'AE BioSamples Test', "extension":"tabular"}]
    json_biosamples_response = json.dumps(biosamples_response)
    print json_biosamples_response
    #NOTE: Use Python Libraries to parameterize URL
    return json_biosamples_response


def _get_samples(url):
    """ 
    Use search term and BioSamples 'findByText' API (https://www.ebi.ac.uk/biosamples/help/api).
    """
    all_sample_accessions = []
    all_sample_data = {}

    r = requests.get(url, headers={"Accept": "application/json"})
    if r.status_code == 200:
        response = r.text
        data = json.loads(response)

        if 'next' in data['_links']:
            sample_list = data['_embedded']['samples']
            for sample in sample_list:
                accession = sample['accession']
                name = sample['name']
                description = sample['description']
                all_sample_data['accession'] = accession
                all_sample_accessions.append(all_sample_data.copy())
            return all_sample_accessions + _get_samples(data['_links']['next']['href'])
        else:
            sample_list = data['_embedded']['samples']
            for sample in sample_list:
                accession = sample['accession']
                name = sample['name']
                description = sample['description']
                all_sample_data['accession'] = accession
                all_sample_data['name'] = name
                if description:
                    all_sample_data['description'] = description
                else:
                    all_sample_data['description'] = 'None'
                all_sample_accessions.append(all_sample_data.copy())
            return all_sample_accessions
    else:
        r.raise_for_status()



# @app.route("/fetch/")
# def fetch():
#     print "** Fetch called" #Not using this right now
#     """Route for Galaxy to fetch data at

#     4. When Galaxy receives the parameters it will run a URL fetching process
#     in the background that will resubmit the parameters to the datasource, and it
#     will deposit the returned data in the user's account.
#     """

#     # response = ['#Key\tValue']
#     # for key in request.args:
#     #     response.append('%s\t%s' % (key, request.args[key]))
#     # return '\n'.join(response)

#     biosamples_response = [{'url': 'ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR143/001/ERR1433121/ERR1433121.fastq.gz', 'name': 'AE BioSamples Test', "extension":"tabular"}]

#     # {'url': 'http://www.ebi.ac.uk/arrayexpress/files/E-MTAB-4758/E-MTAB-4758.idf.txt', 'name': 'AE BioSamples Test', "extension":"tabular"}]
#     print type(biosamples_response)

#     json_biosamples_response = json.dumps(biosamples_response)
#     # return json_biosamples_response
#     url_for_galaxy = "http://localhost:4000/get_data_for_galaxy"
#     return url_for_galaxy



@app.route("/export/")
def export():
    print "** Export called"
    """Return user to Galaxy and provide URL to fetch data from.

    3. At the point where the parameter submission would return data, the external
    datasource will have to instead post these parameters to the url that were sent
    in the GALAXY_URL parameter. Typically this would require that the action
    attribute of the form that generates data to be pointed to the value sent in
    the GALAXY_URL parameter.
    """
    print "I'm here now - 0"
    print request.method

    sample_values = session['all_samples']
    print "** ALL Samples - EXPORT(): ", sample_values
    sample_values_url_param = ','.join(sample_values)

    # Extract the Galaxy URL to redirect the user to from the parameters (or any other suitable source like session data)
    try:
        # return_to_galaxy = request.args['GALAXY_URL']
        # update to get Galaxy URL from Flask Session
        return_to_galaxy = urllib.unquote(session['gx_url'])
        print "** GX_URL: ", return_to_galaxy
    except Exception as e:
        print e

    print "I'm here now - 1"
    # Construct the URL to fetch data from. That page should respond with the
    # entire content that you wish to go into a dataset (no
    # partials/paginated/javascript/etc)
    # fetch_url = 'http://localhost:4000/fetch/?var=1&b=23' # ORIGINAL

    # fetch_url = 'http://localhost:4000/fetch/?ae_link=http://www.ebi.ac.uk/arrayexpress/experiments/E-MTAB-4104/'
    # fetch_url = 'http://www.ebi.ac.uk/biosamples/api/samplesrelations/SAMEA4084308/externalLinks' # TEST
    # fetch_url = 'https://www.ebi.ac.uk/biosamples/api/samples/SAMEA4084308'

    # TODO: Galaxy Hackathon - Change to call function in this file to do the work to get the files to exprt to Galxay
    # fetch_url = 'http://localhost:4000/fetch/'

    bsd_url = 'http://localhost:4000/get_data_for_galaxy/?sample_list='+sample_values_url_param
    print "BSD_PARAMS_URL: ", bsd_url, type(str(bsd_url))


    # Must provide some parameters to Galaxy
    params = {
            # 'URL': 'http://localhost:4000/get_data_for_galaxy/',
            'URL': bsd_url,
            # You can set the dataset type, should be a Galaxy datatype name
            'type': 'tabular',
            # And the output filename
            'name': 'SyncDataset Name - BioSamples',
            }


    # Found on the web, update an existing URL with possible additional parameters
    url_parts = list(urlparse.urlparse(return_to_galaxy))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    query.update(params)
    url_parts[4] = urllib.urlencode(query)
    redir = urlparse.urlunparse(url_parts)
    print "** REDIRECT URL: ", redir

    print "I'm here now - 2"

    # Then redirect the user to Galaxy
    return redirect(redir, code=302)
    # Galaxy will subsequently make a request to `fetch_url`

if __name__ == "__main__":
    app.secret_key = 'my_secret_key'
    app.run(host='0.0.0.0', port=4000, debug=True)


