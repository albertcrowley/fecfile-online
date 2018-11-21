from django.conf.urls import url
from . import views

# url's for comm_info and get_default_reasons for filing

urlpatterns = [
    url(r'^f99/fetch_f99_info$', views.fetch_f99_info, name='fetch_f99_info' ),
    url(r'^f99/create_f99_info$', views.create_f99_info, name='create_f99_info'),
    url(r'^f99/update_f99_info$', views.update_f99_info, name='update_f99_info'),
    url(r'^f99/get_default_reasons$', views.get_f99_reasons, name='get_f99_reasons'),
    url(r'^f99/submit_comm_info$', views.submit_comm_info, name='submit_comm_info'),
    url(r'^f99/validate_f99$', views.validate_f99, name='validate_f99'),
    url(r'^f99/get_signee$', views.get_signee, name='get_signee' ),
    url(r'^f99/get_rad_analyst_info$', views.get_rad_analyst_info, name='get_rad_analyst_info' ),    
    url(r'^f99/get_form99list$', views.get_form99list, name='get_form99list' ),
    #url(r'^f99/print_f99_info$', views.print_f99_info, name='print_f99_info' ),
    #url(r'^f99/f99_file_upload$', views.f99_file_upload, name='f99_file_upload'),
    url(r'^f99/print_pdf_info$', views.print_pdf_info, name='print_pdf_info'),
    url(r'^core/get_committee_details$', views.get_committee, name='get_committee' ),
    url(r'^core/update_committee_details/(?P<cid>[0-9,a-z,A-Z]+)$', views.update_committee, name='update_committee' ),    
    url(r'^core/create_committee$', views.create_committee, name='create_committee')
]