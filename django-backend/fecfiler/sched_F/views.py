from django.shortcuts import render
import datetime
import json
import logging
import os
from decimal import Decimal

import requests
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from fecfiler.core.views import (
    NoOPError,
    check_null_value,
    check_report_id,
    date_format,
    delete_entities,
    get_entities,
    post_entities,
    put_entities,
    remove_entities,
    undo_delete_entities,
)
from fecfiler.core.transaction_util import transaction_exists, update_sched_d_parent
from fecfiler.sched_A.views import get_next_transaction_id
from fecfiler.sched_D.views import do_transaction


# TODO: still need to add line_number and transaction_code to sched_f

# Create your views here.
logger = logging.getLogger(__name__)

MANDATORY_FIELDS_SCHED_F = ["cmte_id", "report_id", "transaction_id"]

# need to validate negative transaction amount
NEGATIVE_SCHED_F_TRANSACTIONS = ["COEXP_PARTY_VOID"]

# need to verify those child memo transactions have:
# 1. back_ref_transaction_id
# 2. parent transaction exist in the db
MEMO_SCHED_F_TRANSACTIONS = [
    "COEXP_CC_PAY_MEMO",
    "COEXP_STAF_REIM_MEMO",
    "COEXP_PMT_PROL_MEMO",
]


def parent_transaction_exists(tran_id, sched_tp):
    """
    check if parent transaction exists
    """
    return transaction_exists(tran_id, sched_tp)


def validate_parent_transaction_exist(data):
    """
    validate parent transaction exsit if saving a child transaction
    """
    if data.get("transaction_type_identifier") in MEMO_SCHED_F_TRANSACTIONS:
        if not data.get("back_ref_transaction_id"):
            raise Exception("Error: parent transaction id missing.")
        elif not parent_transaction_exists(
            data.get("back_ref_transaction_id"), "sched_f"
        ):
            raise Exception("Error: parent transaction not found.")
        else:
            pass


def validate_negative_transaction(data):
    """
    validate transaction amount if negative transaction encounterred.
    """
    if data.get("transaction_type_identifier") in NEGATIVE_SCHED_F_TRANSACTIONS:
        if not float(data.get("expenditure_amount")) < 0:
            raise Exception("current transaction amount need to be negative!")


def check_transaction_id(transaction_id):
    if not (transaction_id[0:2] == "SF"):
        raise Exception(
            "The Transaction ID: {} is not in the specified format."
            + "Transaction IDs start with SF characters".format(transaction_id)
        )
    return transaction_id


def check_mandatory_fields_SF(data):
    """
    validate mandatory fields for sched_e item
    """
    try:
        errors = []
        for field in MANDATORY_FIELDS_SCHED_F:
            if not (field in data and check_null_value(data.get(field))):
                errors.append(field)
        if errors:
            raise Exception(
                "The following mandatory fields are required in order to save data to schedF table: {}".format(
                    ",".join(errors)
                )
            )
    except:
        raise


def schedF_sql_dict(data):
    """
    filter out valid fileds for sched_F

    """
    validate_negative_transaction(data)
    validate_parent_transaction_exist(data)
    valid_fields = [
        "transaction_type_identifier",
        "transaction_id",
        "back_ref_transaction_id",
        "back_ref_sched_name",
        "coordinated_exp_ind",
        "designating_cmte_id",
        "designating_cmte_name",
        "subordinate_cmte_id",
        "subordinate_cmte_name",
        "subordinate_cmte_street_1",
        "subordinate_cmte_street_2",
        "subordinate_cmte_city",
        "subordinate_cmte_state",
        "subordinate_cmte_zip",
        "payee_entity_id",
        "entity_id",
        "expenditure_date",
        "expenditure_amount",
        "aggregate_general_elec_exp",
        "purpose",
        "category_code",
        "payee_cmte_id",
        "memo_code",
        "memo_text",
        "entity_type",
        "entity_name",
        "last_name",
        "first_name",
        "middle_name",
        "suffix",
        "street_1",
        "street_2",
        "city",
        "state",
        "zip_code",
        "prefix",
    ]
    try:
        output = {k: v for k, v in data.items() if k in valid_fields}
        output["payee_cand_id"] = data.get("beneficiary_cand_id")
        output["payee_cand_last_name"] = data.get("cand_last_name")
        output["payee_cand_fist_name"] = data.get("cand_first_name")
        output["payee_cand_middle_name"] = data.get("cand_middle_name")
        output["payee_cand_prefix"] = data.get("cand_prefix")
        output["payee_cand_suffix"] = data.get("cand_suffix")
        output["payee_cand_office"] = data.get("cand_office")
        output["payee_cand_state"] = data.get("cand_office_state")
        output["payee_cand_district"] = data.get("cand_office_district")
        return output
    except:
        raise Exception("invalid request data.")

def get_existing_expenditure_amount(cmte_id, transaction_id):
    """
    fetch existing expenditure amount in the db for current transaction
    """
    _sql = """
    select expenditure_amount
    from public.sched_f
    where cmte_id = %s
    and transaction_id = %s
    """
    _v = (cmte_id, transaction_id)
    try:
        with connection.cursor() as cursor:
            cursor.execute(_sql, _v)
            return cursor.fetchone()[0]
    except:
        raise


def put_schedF(data):
    """
    update sched_F item
    here we are assuming entity_id are always referencing something already in our DB
    """
    try:
        check_mandatory_fields_SF(data)
        # check_transaction_id(data.get('transaction_id'))
        if "entity_id" in data:
            get_data = {
                "cmte_id": data.get("cmte_id"),
                "entity_id": data.get("entity_id"),
            }

            # need this update for FEC entity
            if get_data["entity_id"].startswith("FEC"):
                get_data["cmte_id"] = "C00000000"
            prev_entity_list = get_entities(get_data)
            entity_data = put_entities(data)
            entity_flag = True
        else:
            entity_data = post_entities(data)
            entity_flag = False

        existing_expenditure = get_existing_expenditure_amount(
            data.get("cmte_id"), data.get("transaction_id"))
        try:
            entity_id = entity_data.get("entity_id")
            data["payee_entity_id"] = entity_id
            put_sql_schedF(data)

            # if debt payment, need to update debt balance
            if data.get("transaction_type_identifier") == "COEXP_PARTY_DEBT":
                if float(existing_expenditure) != float(data.get("enpenditure_amount")):
                    update_sched_d_parent(
                        data.get("cmte_id"),
                        data.get("back_ref_transaction_id"),
                        data.get("expenditure_amount"),
                        existing_expenditure,
                    )
        except Exception as e:
            # if exceptions saving shced_a, remove entities or rollback entities too
            if entity_flag:
                entity_data = put_entities(prev_entity_list[0])
            else:
                get_data = {"cmte_id": data.get("cmte_id"), "entity_id": entity_id}
                remove_entities(get_data)
            raise Exception(
                "The put_sql_schedF function is throwing an error: " + str(e)
            )
        return data
    except:
        raise


def put_sql_schedF(data):
    """
    update a schedule_f item                    
            
    """
    _sql = """UPDATE public.sched_f
              SET transaction_type_identifier= %s, 
                  back_ref_transaction_id= %s,
                  back_ref_sched_name= %s,
                  coordinated_exp_ind= %s,
                  designating_cmte_id= %s,
                  designating_cmte_name= %s,
                  subordinate_cmte_id= %s,
                  subordinate_cmte_name= %s,
                  subordinate_cmte_street_1= %s,
                  subordinate_cmte_street_2= %s,
                  subordinate_cmte_city= %s,
                  subordinate_cmte_state= %s,
                  subordinate_cmte_zip= %s,
                  payee_entity_id= %s,
                  expenditure_date= %s,
                  expenditure_amount = %s,
                  aggregate_general_elec_exp= %s,
                  purpose= %s,
                  category_code= %s,
                  payee_cmte_id= %s,
                  payee_cand_id= %s,
                  payee_cand_last_name= %s,
                  payee_cand_fist_name= %s,
                  payee_cand_middle_name= %s,
                  payee_cand_prefix= %s,
                  payee_cand_suffix= %s,
                  payee_cand_office= %s,
                  payee_cand_state= %s,
                  payee_cand_district= %s,
                  memo_code= %s,
                  memo_text= %s,
                  last_update_date= %s
              WHERE transaction_id = %s AND report_id = %s AND cmte_id = %s 
              AND delete_ind is distinct from 'Y';
        """
    _v = (
        data.get("transaction_type_identifier", ""),
        data.get("back_ref_transaction_id", ""),
        data.get("back_ref_sched_name", ""),
        data.get("coordinated_exp_ind", ""),
        data.get("designating_cmte_id", ""),
        data.get("designating_cmte_name", ""),
        data.get("subordinate_cmte_id", ""),
        data.get("subordinate_cmte_name", ""),
        data.get("subordinate_cmte_street_1", ""),
        data.get("subordinate_cmte_street_2", ""),
        data.get("subordinate_cmte_city", ""),
        data.get("subordinate_cmte_state", ""),
        data.get("subordinate_cmte_zip", ""),
        data.get("payee_entity_id", ""),
        data.get("expenditure_date", None),
        data.get("expenditure_amount", None),
        data.get("aggregate_general_elec_exp", None),
        data.get("purpose", ""),
        data.get("category_code", ""),
        data.get("payee_cmte_id", ""),
        data.get("payee_cand_id", ""),
        data.get("payee_cand_last_name", ""),
        data.get("payee_cand_fist_name", ""),
        data.get("payee_cand_middle_name", ""),
        data.get("payee_cand_prefix", ""),
        data.get("payee_cand_suffix", ""),
        data.get("payee_cand_office", ""),
        data.get("payee_cand_state", ""),
        data.get("payee_cand_district", ""),
        data.get("memo_code", ""),
        data.get("memo_text", ""),
        datetime.datetime.now(),
        data.get("transaction_id"),
        data.get("report_id"),
        data.get("cmte_id"),
    )
    do_transaction(_sql, _v)


def validate_sF_data(data):
    """
    validate sF json data
    """
    check_mandatory_fields_SF(data)


def post_schedF(data):
    """
    function for handling POST request for sF, need to:
    1. generatye new transaction_id
    2. validate data
    3. save data to db
    """
    try:
        # check_mandatory_fields_SA(datum, MANDATORY_FIELDS_SCHED_A)
        data["transaction_id"] = get_next_transaction_id("SF")
        validate_sF_data(data)
        if "entity_id" in data:
            get_data = {
                "cmte_id": data.get("cmte_id"),
                "entity_id": data.get("entity_id"),
            }

            # need this update for FEC entity
            if get_data["entity_id"].startswith("FEC"):
                get_data["cmte_id"] = "C00000000"
            prev_entity_list = get_entities(get_data)
            entity_data = put_entities(data)
            entity_flag = True
        else:
            entity_data = post_entities(data)
            entity_flag = False
        try:
            entity_id = entity_data.get("entity_id")
            data["payee_entity_id"] = entity_id
            logger.debug(data)
            post_sql_schedF(data)
            # update sched_d parent if coexp debt payment
            if data.get("transaction_type_identifier") == "COEXP_PARTY_DEBT":
                update_sched_d_parent(
                    data.get("cmte_id"),
                    data.get("back_ref_transaction_id"),
                    data.get("expenditure_amount"),
                )
        except Exception as e:
            # if exceptions saving shced_a, remove entities or rollback entities too
            if entity_flag:
                entity_data = put_entities(prev_entity_list[0])
            else:
                get_data = {"cmte_id": data.get("cmte_id"), "entity_id": entity_id}
                remove_entities(get_data)
            raise Exception(
                "The post_sql_schedF function is throwing an error: " + str(e)
            )
        return data
    except:
        raise


def post_sql_schedF(data):
    try:
        _sql = """
        INSERT INTO public.sched_f (
            cmte_id,
            report_id,
            transaction_type_identifier,
            transaction_id, 
            back_ref_transaction_id,
            back_ref_sched_name,
            coordinated_exp_ind,
            designating_cmte_id,
            designating_cmte_name,
            subordinate_cmte_id,
            subordinate_cmte_name,
            subordinate_cmte_street_1,
            subordinate_cmte_street_2,
            subordinate_cmte_city,
            subordinate_cmte_state,
            subordinate_cmte_zip,
            payee_entity_id,
            expenditure_date,
            expenditure_amount,
            aggregate_general_elec_exp,
            purpose,
            category_code,
            payee_cmte_id,
            payee_cand_id,
            payee_cand_last_name,
            payee_cand_fist_name,
            payee_cand_middle_name,
            payee_cand_prefix,
            payee_cand_suffix,
            payee_cand_office,
            payee_cand_state,
            payee_cand_district,
            memo_code,
            memo_text,
            create_date,
            last_update_date
            )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s); 
        """
        _v = (
            data.get("cmte_id"),
            data.get("report_id"),
            data.get("transaction_type_identifier", ""),
            data.get("transaction_id", ""),
            data.get("back_ref_transaction_id", ""),
            data.get("back_ref_sched_name", ""),
            data.get("coordinated_exp_ind", ""),
            data.get("designating_cmte_id", ""),
            data.get("designating_cmte_name", ""),
            data.get("subordinate_cmte_id", ""),
            data.get("subordinate_cmte_name", ""),
            data.get("subordinate_cmte_street_1", ""),
            data.get("subordinate_cmte_street_2", ""),
            data.get("subordinate_cmte_city", ""),
            data.get("subordinate_cmte_state", ""),
            data.get("subordinate_cmte_zip", ""),
            data.get("payee_entity_id", ""),
            data.get("expenditure_date", None),
            data.get("expenditure_amount", None),
            data.get("aggregate_general_elec_exp", None),
            data.get("purpose", ""),
            data.get("category_code", ""),
            data.get("payee_cmte_id", ""),
            data.get("payee_cand_id", ""),
            data.get("payee_cand_last_name", ""),
            data.get("payee_cand_fist_name", ""),
            data.get("payee_cand_middle_name", ""),
            data.get("payee_cand_prefix", ""),
            data.get("payee_cand_suffix", ""),
            data.get("payee_cand_office", ""),
            data.get("payee_cand_state", ""),
            data.get("payee_cand_district", ""),
            data.get("memo_code", ""),
            data.get("memo_text", ""),
            datetime.datetime.now(),
            datetime.datetime.now(),
        )
        with connection.cursor() as cursor:
            # Insert data into schedD table
            cursor.execute(_sql, _v)
    except Exception:
        raise


def get_schedF(data):
    """
    load sched_F data based on cmte_id, report_id and transaction_id
    """
    try:
        cmte_id = data.get("cmte_id")
        report_id = data.get("report_id")
        if "transaction_id" in data:
            transaction_id = check_transaction_id(data.get("transaction_id"))
            forms_obj = get_list_schedF(report_id, cmte_id, transaction_id)
        else:
            forms_obj = get_list_all_schedF(report_id, cmte_id)
        return forms_obj
    except:
        raise


def get_list_all_schedF(report_id, cmte_id):

    try:
        with connection.cursor() as cursor:
            # GET single row from schedA table
            _sql = """SELECT json_agg(t) FROM ( SELECT
            cmte_id,
            report_id,
            transaction_type_identifier,
            transaction_id, 
            back_ref_transaction_id,
            back_ref_sched_name,
            coordinated_exp_ind,
            designating_cmte_id,
            designating_cmte_name,
            subordinate_cmte_id,
            subordinate_cmte_name,
            subordinate_cmte_street_1,
            subordinate_cmte_street_2,
            subordinate_cmte_city,
            subordinate_cmte_state,
            subordinate_cmte_zip,
            payee_entity_id as entity_id,
            expenditure_date,
            expenditure_amount,
            aggregate_general_elec_exp,
            purpose,
            category_code,
            payee_cmte_id,
            payee_cand_id as beneficiary_cand_id,
            payee_cand_last_name as cand_last_name,
            payee_cand_fist_name as cand_first_name,
            payee_cand_middle_name as cand_middle_name,
            payee_cand_prefix as cand_prefix,
            payee_cand_suffix as cand_suffix,
            payee_cand_office as cand_office,
            payee_cand_state as cand_office_state,
            payee_cand_district as cand_office_district,
            memo_code,
            memo_text,
            delete_ind,
            create_date,
            last_update_date
            FROM public.sched_f
            WHERE report_id = %s AND cmte_id = %s
            AND delete_ind is distinct from 'Y') t
            """
            cursor.execute(_sql, (report_id, cmte_id))
            schedF_list = cursor.fetchone()[0]
            if schedF_list is None:
                raise NoOPError(
                    "No sched_F transaction found for report_id {} and cmte_id: {}".format(
                        report_id, cmte_id
                    )
                )
            merged_list = []
            for dictF in schedF_list:
                entity_id = dictF.get("entity_id")
                data = {"entity_id": entity_id, "cmte_id": cmte_id}
                entity_list = get_entities(data)
                dictEntity = entity_list[0]
                merged_dict = {**dictF, **dictEntity}
                merged_list.append(merged_dict)
        return merged_list
    except Exception:
        raise


def get_list_schedF(report_id, cmte_id, transaction_id):
    try:
        with connection.cursor() as cursor:
            # GET single row from schedA table
            _sql = """SELECT json_agg(t) FROM ( SELECT
            sf.cmte_id,
            sf.report_id,
            sf.transaction_type_identifier,
            sf.transaction_id, 
            sf.back_ref_transaction_id,
            sf.back_ref_sched_name,
            sf.coordinated_exp_ind,
            sf.designating_cmte_id,
            sf.designating_cmte_name,
            sf.subordinate_cmte_id,
            sf.subordinate_cmte_name,
            sf.subordinate_cmte_street_1,
            sf.subordinate_cmte_street_2,
            sf.subordinate_cmte_city,
            sf.subordinate_cmte_state,
            sf.subordinate_cmte_zip,
            sf.payee_entity_id as entity_id,
            sf.expenditure_date,
            sf.expenditure_amount,
            sf.aggregate_general_elec_exp,
            sf.purpose,
            sf.category_code,
            sf.payee_cmte_id,
            sf.payee_cand_id as beneficiary_cand_id,
            sf.payee_cand_last_name as cand_last_name,
            sf.payee_cand_fist_name as cand_first_name,
            sf.payee_cand_middle_name as cand_middle_name,
            sf.payee_cand_prefix as cand_prefix,
            sf.payee_cand_suffix as cand_suffix,
            sf.payee_cand_office as cand_office,
            sf.payee_cand_state as cand_office_state,
            sf.payee_cand_district as cand_office_district,
            sf.memo_code,
            sf.memo_text,
            sf.delete_ind,
            sf.create_date,
            sf.last_update_date,
            (SELECT DISTINCT ON (e.ref_cand_cmte_id) e.entity_id 
            FROM public.entity e WHERE e.entity_id not in (select ex.entity_id from excluded_entity ex where ex.cmte_id = sf.cmte_id) 
                        AND substr(e.ref_cand_cmte_id,1,1) != 'C' AND e.ref_cand_cmte_id = sf.payee_cand_id AND e.delete_ind is distinct from 'Y'
                        ORDER BY e.ref_cand_cmte_id DESC, e.entity_id DESC) AS beneficiary_cand_entity_id
            FROM public.sched_f sf
            WHERE sf.report_id = %s AND sf.cmte_id = %s AND sf.transaction_id = %s
            AND sf.delete_ind is distinct from 'Y') t
            """
            cursor.execute(_sql, (report_id, cmte_id, transaction_id))
            schedF_list = cursor.fetchone()[0]
            if schedF_list is None:
                raise NoOPError(
                    "No sched_f transaction found for transaction_id {}".format(
                        transaction_id
                    )
                )
            merged_list = []
            for dictF in schedF_list:
                entity_id = dictF.get("entity_id")
                data = {"entity_id": entity_id, "cmte_id": cmte_id}
                entity_list = get_entities(data)
                dictEntity = entity_list[0]
                del dictEntity["cand_office"]
                del dictEntity["cand_office_state"]
                del dictEntity["cand_office_district"]
                merged_dict = {**dictF, **dictEntity}
                merged_list.append(merged_dict)
        return merged_list
    except Exception:
        raise


def delete_sql_schedF(cmte_id, report_id, transaction_id):
    """
    do delete sql transaction
    """
    _sql = """UPDATE public.sched_f
            SET delete_ind = 'Y' 
            WHERE transaction_id = %s AND report_id = %s AND cmte_id = %s
        """
    _v = (transaction_id, report_id, cmte_id)
    do_transaction(_sql, _v)


def delete_schedF(data):
    """
    function for handling delete request for se
    """
    try:

        delete_sql_schedF(
            data.get("cmte_id"), data.get("report_id"), data.get("transaction_id")
        )
    except Exception as e:
        raise


@api_view(["POST", "GET", "DELETE", "PUT"])
def schedF(request):

    if request.method == "POST":
        try:
            cmte_id = request.user.username
            if not ("report_id" in request.data):
                raise Exception("Missing Input: Report_id is mandatory")
            # handling null,none value of report_id
            if not (check_null_value(request.data.get("report_id"))):
                report_id = "0"
            else:
                report_id = check_report_id(request.data.get("report_id"))
            # end of handling
            datum = schedF_sql_dict(request.data)
            datum["report_id"] = report_id
            datum["cmte_id"] = cmte_id
            if "transaction_id" in request.data and check_null_value(
                request.data.get("transaction_id")
            ):
                datum["transaction_id"] = check_transaction_id(
                    request.data.get("transaction_id")
                )
                data = put_schedF(datum)
            else:
                print(datum)
                data = post_schedF(datum)
            # Associating child transactions to parent and storing them to DB

            update_aggregate_general_elec_exp(
                datum["cmte_id"], datum["payee_cand_id"], datum["expenditure_date"]
            )
            output = get_schedF(data)
            return JsonResponse(output[0], status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                "The schedF API - POST is throwing an exception: " + str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

    elif request.method == "GET":
        try:
            data = {"cmte_id": request.user.username}
            if "report_id" in request.query_params and check_null_value(
                request.query_params.get("report_id")
            ):
                data["report_id"] = check_report_id(
                    request.query_params.get("report_id")
                )
            else:
                raise Exception("Missing Input: report_id is mandatory")
            if "transaction_id" in request.query_params and check_null_value(
                request.query_params.get("transaction_id")
            ):
                data["transaction_id"] = check_transaction_id(
                    request.query_params.get("transaction_id")
                )
            datum = get_schedF(data)
            return JsonResponse(datum, status=status.HTTP_200_OK, safe=False)
        except NoOPError as e:
            logger.debug(e)
            forms_obj = []
            return JsonResponse(
                forms_obj, status=status.HTTP_204_NO_CONTENT, safe=False
            )
        except Exception as e:
            logger.debug(e)
            return Response(
                "The schedF API - GET is throwing an error: " + str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

    elif request.method == "DELETE":
        try:
            data = {"cmte_id": request.user.username}
            if "report_id" in request.data and check_null_value(
                request.data.get("report_id")
            ):
                data["report_id"] = check_report_id(request.data.get("report_id"))
            else:
                raise Exception("Missing Input: report_id is mandatory")
            if "transaction_id" in request.data and check_null_value(
                request.data.get("transaction_id")
            ):
                data["transaction_id"] = check_transaction_id(
                    request.data.get("transaction_id")
                )
            else:
                raise Exception("Missing Input: transaction_id is mandatory")
            datum = get_schedF(data)[0]
            delete_schedF(data)
            update_aggregate_general_elec_exp(
                datum["cmte_id"],
                datum["beneficiary_cand_id"],
                datetime.datetime.strptime(datum.get("expenditure_date"), "%Y-%m-%d")
                .date()
                .strftime("%m/%d/%Y"),
            )
            return Response(
                "The Transaction ID: {} has been successfully deleted".format(
                    data.get("transaction_id")
                ),
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                "The schedF API - DELETE is throwing an error: " + str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

    elif request.method == "PUT":
        try:
            datum = schedF_sql_dict(request.data)
            if "transaction_id" in request.data and check_null_value(
                request.data.get("transaction_id")
            ):
                datum["transaction_id"] = request.data.get("transaction_id")
            else:
                raise Exception("Missing Input: transaction_id is mandatory")

            if not ("report_id" in request.data):
                raise Exception("Missing Input: Report_id is mandatory")
            # handling null,none value of report_id
            if not (check_null_value(request.data.get("report_id"))):
                report_id = "0"
            else:
                report_id = check_report_id(request.data.get("report_id"))
            # end of handling
            datum["report_id"] = report_id
            datum["cmte_id"] = request.user.username

            # if 'entity_id' in request.data and check_null_value(request.data.get('entity_id')):
            #     datum['entity_id'] = request.data.get('entity_id')
            # if request.data.get('transaction_type') in CHILD_SCHED_B_TYPES:
            #     data = put_schedB(datum)
            #     output = get_schedB(data)
            # else:
            data = put_schedF(datum)
            # output = get_schedA(data)
            update_aggregate_general_elec_exp(
                datum["cmte_id"], datum["payee_cand_id"], datum["expenditure_date"]
            )
            output = get_schedF(data)
            return JsonResponse(output[0], status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.debug(e)
            return Response(
                "The schedF API - PUT is throwing an error: " + str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

    else:
        raise NotImplementedError


"""
TO GET THE AGGREGATE FOR EXPENDITURE AMOUNT FOR CANDIDATE PER GENERAL ELECTION
"""


@api_view(["GET"])
def get_aggregate_general_elec_exp(request):
    try:
        aggregate_amount = 0.0
        cmte_id = request.user.username
        mandatory_fields = ["beneficiary_cand_id", "expenditure_date"]
        for field in mandatory_fields:
            if request.query_params.get(field) in [None, "", "", " ", "Null", "None"]:
                raise Exception(
                    "Mandatory fields are missing in the request parameters. The mandatory fields are: "
                    + ",".join(mandatory_fields)
                )
        beneficiary_cand_id = request.query_params.get("beneficiary_cand_id")
        # election_year = request.query_params.get('election_year')
        expenditure_date = request.query_params.get("expenditure_date")
        expenditure_amount = request.query_params.get("expenditure_amount", 0.0)
        cvg_start_date, cvg_end_date = agg_dates(
            cmte_id, beneficiary_cand_id, expenditure_date
        )
        logger.debug("cvg_start_date:" + str(cvg_start_date))
        logger.debug("cvg_end_date:" + str(cvg_end_date))
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT aggregate_general_elec_exp FROM public.sched_f WHERE payee_cand_id = %s AND expenditure_date >= %s AND
                expenditure_date <= %s AND expenditure_date <= %s ORDER BY expenditure_date DESC, create_date DESC """,
                [beneficiary_cand_id, cvg_start_date, cvg_end_date, expenditure_date],
            )
            if cursor.rowcount != 0:
                aggregate_amount = cursor.fetchone()[0]
                if not aggregate_amount:
                    aggregate_amount = 0.0
        return JsonResponse(
            {
                "aggregate_general_elec_exp": float(expenditure_amount)
                + float(aggregate_amount)
            },
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        logger.debug(e)
        return Response(
            "The get_aggregate_general_elec_exp API is throwing an error: " + str(e),
            status=status.HTTP_400_BAD_REQUEST,
        )


def agg_dates(cmte_id, beneficiary_cand_id, expenditure_date):
    try:
        start_date = None
        end_date = None
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT json_agg(t) FROM (SELECT e.cand_office, e.cand_office_state, e.cand_office_district FROM public.entity e 
                WHERE e.cmte_id in ('C00000000') 
                AND substr(e.ref_cand_cmte_id,1,1) != 'C' AND e.ref_cand_cmte_id = %s AND e.delete_ind is distinct from 'Y') as t""",
                [beneficiary_cand_id],
            )
            # print(cursor.query)
            cand = cursor.fetchone()[0]
            logger.debug("Candidate Office Data: " + str(cand))
        if cand:
            cand = cand[0]
            if cand["cand_office"] == "H":
                add_year = 1
                if not (cand["cand_office_state"] and cand["cand_office_district"]):
                    raise Exception(
                        "The candidate details for candidate Id: {} are missing: office state and district".format(
                            beneficiary_cand_id
                        )
                    )
            elif cand["cand_office"] == "S":
                add_year = 5
                if not cand["cand_office_state"]:
                    raise Exception(
                        "The candidate details for candidate Id: {} are missing: office state".format(
                            beneficiary_cand_id
                        )
                    )
                cand["cand_office_district"] = None
            elif cand["cand_office"] == "P":
                add_year = 3
                cand["cand_office_state"] = None
                cand["cand_office_district"] = None
            else:
                raise Exception(
                    "The candidate id: {} does not belong to either Senate, House or Presidential office. Kindly check cand_office in entity table for details".format(
                        beneficiary_cand_id
                    )
                )
        else:
            raise Exception(
                "The candidate Id: {} is not present in the entity table.".format(
                    beneficiary_cand_id
                )
            )
        election_year_list = get_election_year(
            cand["cand_office"], cand["cand_office_state"], cand["cand_office_district"]
        )
        logger.debug("Election years based on FEC API:" + str(election_year_list))
        expenditure_year = (
            datetime.datetime.strptime(expenditure_date, "%m/%d/%Y").date().year
        )
        for i, val in enumerate(election_year_list):
            if i == len(election_year_list) - 2:
                break
            if (
                election_year_list[i + 1] < expenditure_year
                and expenditure_year <= election_year_list[i]
            ):
                end_date = datetime.date(election_year_list[i], 12, 31)
                start_year = election_year_list[i] - add_year
                start_date = datetime.date(start_year, 1, 1)
        if not end_date:
            if datetime.datetime.now().year % 2 == 1:
                end_year = datetime.datetime.now().year + add_year
                end_date = datetime.date(end_year, 12, 31)
                start_date = datetime.date(datetime.datetime.now().year, 1, 1)
            else:
                end_date = datetime.date(datetime.datetime.now().year, 12, 31)
                start_year = datetime.datetime.now().year - add_year
                start_date = datetime.date(start_year, 1, 1)
        return start_date, end_date
    except Exception as e:
        logger.debug(e)
        raise Exception("The agg_dates function is throwing an error: " + str(e))


def update_aggregate_general_elec_exp(cmte_id, beneficiary_cand_id, expenditure_date):
    try:
        aggregate_amount = 0.0
        # expenditure_date = datetime.datetime.strptime(expenditure_date, '%Y-%m-%d').date()
        cvg_start_date, cvg_end_date = agg_dates(
            cmte_id, beneficiary_cand_id, expenditure_date
        )
        transaction_list = get_SF_transactions_candidate(
            cvg_start_date, cvg_end_date, beneficiary_cand_id
        )
        for transaction in transaction_list:
            if transaction["memo_code"] != "X":
                aggregate_amount += float(transaction["expenditure_amount"])
            if transaction["expenditure_date"] >= expenditure_date:
                put_aggregate_SF(aggregate_amount, transaction["transaction_id"])
    except Exception as e:
        logger.debug(e)
        raise Exception(
            "The update_aggregate_general_elec_exp API is throwing an error: " + str(e)
        )


def get_SF_transactions_candidate(start_date, end_date, beneficiary_cand_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT json_agg(t) FROM (SELECT t1.transaction_id, t1.expenditure_date, t1.expenditure_amount, 
                t1.aggregate_general_elec_exp, t1.memo_code FROM public.sched_f t1 WHERE t1.payee_cand_id = %s AND t1.expenditure_date >= %s AND 
                t1.expenditure_date <= %s AND t1.delete_ind is distinct FROM 'Y' 
                AND (SELECT t2.delete_ind FROM public.reports t2 WHERE t2.report_id = t1.report_id) is distinct FROM 'Y'
                ORDER BY t1.expenditure_date ASC, t1.create_date ASC) t""",
                [beneficiary_cand_id, start_date, end_date],
            )
            if cursor.rowcount == 0:
                transaction_list = []
            else:
                transaction_list = cursor.fetchall()[0][0]
        logger.debug(transaction_list)
        return transaction_list
    except Exception as e:
        logger.debug(e)
        raise Exception(
            "The get_SF_transactions_candidate function is throwing an error: " + str(e)
        )


def put_aggregate_SF(aggregate_general_elec_exp, transaction_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.sched_f SET aggregate_general_elec_exp = %s WHERE transaction_id = %s",
                [aggregate_general_elec_exp, transaction_id],
            )
            if cursor.rowcount == 0:
                raise Exception(
                    "The Transaction ID: {} does not exist in schedF table".format(
                        transaction_id
                    )
                )
    except Exception as e:
        logger.debug(e)
        raise Exception("The put_aggregate_SF function is throwing an error: " + str(e))


def get_election_year(office_sought, election_state, election_district):
    try:
        if office_sought == "P":
            param_string = "&office_sought={}".format(office_sought)
            add_year = 4
        elif office_sought == "S":
            param_string = "&office_sought={}&election_state={}".format(
                office_sought, election_state
            )
            add_year = 6
        elif office_sought == "H":
            param_string = "&office_sought={}&election_state={}&election_district={}".format(
                office_sought, election_state, election_district
            )
            add_year = 2
        else:
            raise Exception("office_sought can only take P,S,H values")
        i = 1
        results = []
        election_year_list = []
        while True:
            ab = requests.get(
                "https://api.open.fec.gov/v1/election-dates/?sort=-election_date&api_key=50nTHLLMcu3XSSzLnB0hax2Jg5LFniladU5Yf25j&page={}&per_page=100&sort_hide_null=false&sort_nulls_last=false{}".format(
                    i, param_string
                )
            )
            results = results + ab.json()["results"]
            if (
                i == ab.json()["pagination"]["pages"]
                or ab.json()["pagination"]["pages"] == 0
            ):
                break
            else:
                i += 1
        logger.debug("count of FEC election dates API:" + str(len(results)))
        for result in results:
            if result["election_year"] not in election_year_list:
                election_year_list.append(result["election_year"])
        if election_year_list:
            election_year_list.sort(reverse=True)
            if election_year_list[0] + add_year >= datetime.datetime.now().year:
                election_year_list.insert(0, election_year_list[0] + add_year)
        return election_year_list
    except Exception as e:
        logger.debug(e)
        raise Exception(
            "The get_election_year function is throwing an error: " + str(e)
        )
