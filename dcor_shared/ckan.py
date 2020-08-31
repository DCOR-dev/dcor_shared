import ckan.lib.uploader as uploader
import ckan.plugins.toolkit as toolkit


def get_dataset_path(context, resource):
    resource_id = resource["id"]
    rsc = toolkit.get_action('resource_show')(context, {'id': resource_id})
    upload = uploader.ResourceUpload(rsc)
    filepath = upload.get_path(rsc['id'])
    return filepath
