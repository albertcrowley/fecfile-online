import { Component, OnInit, OnDestroy, OnChanges, Output, EventEmitter, Input, SimpleChanges, ViewEncapsulation } from '@angular/core';
import { IndividualReceiptComponent } from '../form-3x/individual-receipt/individual-receipt.component';
import { FormBuilder, FormGroup, FormControl, NgForm, Validators } from '@angular/forms';
import { FormsService } from 'src/app/shared/services/FormsService/forms.service';
import { IndividualReceiptService } from '../form-3x/individual-receipt/individual-receipt.service';
import { ContactsService } from 'src/app/contacts/service/contacts.service';
import { ActivatedRoute, Router } from '@angular/router';
import { NgbTooltipConfig } from '@ng-bootstrap/ng-bootstrap';
import { UtilService } from 'src/app/shared/utils/util.service';
import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { ReportTypeService } from '../form-3x/report-type/report-type.service';
import { TypeaheadService } from 'src/app/shared/partials/typeahead/typeahead.service';
import { DialogService } from 'src/app/shared/services/DialogService/dialog.service';
import { F3xMessageService } from '../form-3x/service/f3x-message.service';
import { TransactionsMessageService } from '../transactions/service/transactions-message.service';
import { ContributionDateValidator } from 'src/app/shared/utils/forms/validation/contribution-date.validator';
import { TransactionsService } from '../transactions/service/transactions.service';
import { HttpClient } from '@angular/common/http';
import { MessageService } from 'src/app/shared/services/MessageService/message.service';
import { ScheduleActions } from '../form-3x/individual-receipt/schedule-actions.enum';
import { AbstractSchedule } from '../form-3x/individual-receipt/abstract-schedule';
import { ReportsService } from 'src/app/reports/service/report.service';
import { TransactionModel } from '../transactions/model/transaction.model';
import { Observable, Subscription } from 'rxjs';
import { style, animate, transition, trigger } from '@angular/animations';
import { PaginationInstance } from 'ngx-pagination';
import { SortableColumnModel } from 'src/app/shared/services/TableService/sortable-column.model';
import { TableService } from 'src/app/shared/services/TableService/table.service';
import { SchedLService } from './sched-l.service';
import { SchedLModel } from './sched-l.model';
import { AbstractScheduleParentEnum } from '../form-3x/individual-receipt/abstract-schedule-parent.enum';

@Component({
  selector: 'app-sched-l',
  templateUrl: './sched-l.component.html',
  styleUrls: ['./sched-l.component.scss'],
  providers: [NgbTooltipConfig, CurrencyPipe, DecimalPipe],
  encapsulation: ViewEncapsulation.None,
  animations: [
    trigger('fadeInOut', [
      transition(':enter', [
        style({ opacity: 0 }),
        animate(500, style({ opacity: 1 }))
      ]),
      transition(':leave', [
        animate(0, style({ opacity: 0 }))
      ])
    ])
  ]
})
export class SchedLComponent extends AbstractSchedule implements OnInit, OnDestroy, OnChanges {
  @Input() transactionTypeText: string;
  @Input() transactionType: string;
  @Input() scheduleAction: ScheduleActions;
  @Input() scheduleType: string;
  @Output() status: EventEmitter<any>;

  public formType: string;
  public showPart2: boolean;
  public loaded = false;
  public schedL: FormGroup;


  public lSubscription: Subscription;
  public lSum: any;
  public saveLRes: any;

  public tableConfig: any;

  public showSelectType = true;

  public schedLsModel: Array<SchedLModel>;
  public schedLsModelL: Array<SchedLModel>;

  constructor(
    _http: HttpClient,
    _fb: FormBuilder,
    _formService: FormsService,
    _receiptService: IndividualReceiptService,
    _contactsService: ContactsService,
    _activatedRoute: ActivatedRoute,
    _config: NgbTooltipConfig,
    _router: Router,
    _utilService: UtilService,
    _messageService: MessageService,
    _currencyPipe: CurrencyPipe,
    _decimalPipe: DecimalPipe,
    _reportTypeService: ReportTypeService,
    _typeaheadService: TypeaheadService,
    _dialogService: DialogService,
    _f3xMessageService: F3xMessageService,
    _transactionsMessageService: TransactionsMessageService,
    _contributionDateValidator: ContributionDateValidator,
    _transactionsService: TransactionsService,
    _reportsService: ReportsService,
    private _actRoute: ActivatedRoute,
    private _schedLService: SchedLService,
    private _individualReceiptService: IndividualReceiptService,
    private _tranMessageService: TransactionsMessageService,
  ) {
     super(
      _http,
      _fb,
      _formService,
      _receiptService,
      _contactsService,
      _activatedRoute,
      _config,
      _router,
      _utilService,
      _messageService,
      _currencyPipe,
      _decimalPipe,
      _reportTypeService,
      _typeaheadService,
      _dialogService,
      _f3xMessageService,
      _transactionsMessageService,
      _contributionDateValidator,
      _transactionsService,
      _reportsService
    );
    _schedLService;
    _individualReceiptService;
    _tranMessageService;
  }


  public ngOnInit() {
    this.abstractScheduleComponent = AbstractScheduleParentEnum.schedLComponent;
    // temp code - waiting until dynamic forms completes and loads the formGroup
    // before rendering the static fields, otherwise validation error styling
    // is not working (input-error-field class).  If dynamic forms deliver,
    // the static fields, then remove this or set a flag when formGroup is ready
    setTimeout(() => {
      this.loaded = true;
    }, 2000);

    this.formType = this._actRoute.snapshot.paramMap.get('form_id');
    //this.getH4Sum(this._individualReceiptService.getReportIdFromStorage(this.formType));
    
    //this.setSchedH4();

    this.tableConfig = {
      itemsPerPage: 8,
      currentPage: 1,
      totalItems: 10
    };

    //this.setDefaultValues();

    /*
    console.log("this.transactionType: ", this.transactionType);
    if(this.transactionType === 'ALLOC_H4_RATIO') {
      this.transactionType = 'ALLOC_EXP_DEBT'
    }
    */

    this.setSchedL();

  }

  pageChanged(event){
    this.tableConfig.currentPage = event;
  }

  public ngOnChanges(changes: SimpleChanges) {
    // OnChanges() can be triggered before OnInit().  Ensure formType is set.
    this.formType = '3X';

    if (this.transactionType === 'LA_SUM' || this.transactionType === 'LB_SUM') {
      this.getTransactions(this._individualReceiptService.getReportIdFromStorage(this.formType), this.transactionType);
    }

    if (this.transactionType === 'L_SUM') {
      this.getSummary(this._individualReceiptService.getReportIdFromStorage(this.formType), this.transactionType);
    }

  }

  ngDoCheck() {
    this.status.emit({
      otherSchedHTransactionType: this.transactionType
    });
  }

  public ngOnDestroy(): void {
    super.ngOnDestroy();
  }

  /*setDefaultValues() {
    this.schedL.patchValue({levin_account_id: '6'}, { onlySelf: true });
  }*/

  public getReportId(): string {

    let report_id;
    let reportType: any = JSON.parse(localStorage.getItem(`form_${this.formType}_report_type`));
    if (reportType === null || typeof reportType === 'undefined') {
      reportType = JSON.parse(localStorage.getItem(`form_${this.formType}_report_type_backup`));
    }

    if(reportType) {
      if (reportType.hasOwnProperty('reportId')) {
        report_id = reportType.reportId;
      } else if (reportType.hasOwnProperty('reportid')) {
        report_id = reportType.reportid;
      }
    }

    return report_id ? report_id : '0';

  }

  public setSchedL() {
    this.schedL = new FormGroup({
      type: new FormControl('', Validators.required)
    });
  }

  public selectTypeChange(transactionType) {
    this.transactionType = transactionType;
  }
 
  public getTransactions(reportId: string, levinType: string) {
    this.schedLsModel = [];
	
    this.lSubscription = this._schedLService.getTransactions(reportId, levinType).subscribe(res =>
      {
        if (res) {
          /*this.lSum = [];
          this.lSum =  res;
          this.tableConfig.totalItems = res.length;*/
          this.schedLsModelL = this.mapFromServerFields(res);
          this.schedLsModel = this.mapFromServerFields(res);
          this.setArrow(this.schedLsModel);

          //this.schedLsModel = this.schedLsModel .filter(obj => obj.memo_code !== 'X');
          this.tableConfig.totalItems = this.schedLsModel.length;
        }
      });
  }

  public getSummary(reportId: string, levinAccountId: string) {
    //this.schedLsModel = [];
    this.lSubscription = this._schedLService.getSummary(reportId, levinAccountId).subscribe(res =>
      {
        if (res) {
          this.lSum = [];
          this.lSum =  res;
          //this.tableConfig.totalItems = res.length;*/
          //this.schedLsModelL = this.mapFromServerFields(res);
          //this.schedLsModel = this.mapFromServerFields(res);
          //this.setArrow(this.schedLsModel);

          //this.schedLsModel = this.schedLsModel .filter(obj => obj.memo_code !== 'X');
          //this.tableConfig.totalItems = this.schedLsModel.length;
        }
      });
  }
 
  public returnToSum(): void {
    this.transactionType = 'LA_SUM';
    this.getTransactions(this._individualReceiptService.getReportIdFromStorage(this.formType), this.transactionType);
  }

  public returnToAdd(): void {
    this.showSelectType = true;
    this.transactionType = "ALLOC_H4_TYPES"

    //this.transactionType = 'ALLOC_EXP_DEBT'; //'ALLOC_H4_RATIO';
  }1

  public previousStep(): void {
    
    this.schedL.reset();

    this.status.emit({
      form: {},
      direction: 'previous',
      step: 'step_2'
    });
  }

  public clickArrow(item: SchedLModel) {
    if(item.arrow_dir === 'down') {
      let indexRep = this.schedLsModel.indexOf(item);
      if (indexRep > -1) {
        let tmp: Array<SchedLModel> = this.schedLsModelL.filter(obj => obj.back_ref_transaction_id === item.transaction_id);
        for(let entry of tmp) {
          entry.arrow_dir = 'show';
          this.schedLsModel.splice(indexRep + 1, 0, entry);
          indexRep++;
        }
        this.tableConfig.totalItems = this.schedLsModel.length;
      }
      this.schedLsModel.find(function(obj) { return obj.transaction_id === item.transaction_id}).arrow_dir = 'up';

																												   
																															  
	  
    }else if(item.arrow_dir === 'up') {
      //this.schedH4sModel = this.schedH4sModel.filter(obj => obj.memo_code !== 'X');
      this.schedLsModel = this.schedLsModel.filter(obj => obj.back_ref_transaction_id !== item.transaction_id);
      this.tableConfig.totalItems = this.schedLsModel.length;

      this.schedLsModel.find(function(obj) { return obj.transaction_id === item.transaction_id}).arrow_dir = 'down';
    }
   
	 

  }

  public setArrow(items: SchedLModel[]) {
    if (items) {
      for (const item of items) {
        if (item.memo_code !== 'X' && this.schedLsModel.find(function(obj) { return obj.back_ref_transaction_id === item.transaction_id})) {
            item.arrow_dir = 'down';
        }
      }
    }

  }

  public mapFromServerFields(serverData: any) {
    if (!serverData || !Array.isArray(serverData)) {
      return;
    }

    const modelArray: any = [];

    for (const row of serverData) {
      const model = new SchedLModel({});

      model.cmte_id = row.cmte_id;
      model.report_id = row.report_id;
      model.transaction_type_identifier = row.transaction_type_identifier;
      model.tran_desc = row.tran_desc;
      model.transaction_id = row.transaction_id;
      model.back_ref_transaction_id = row.back_ref_transaction_id;
      model.levin_account_id = row.levin_account_id;
      model.levin_account_name = row.levin_account_name;
      model.contribution_date = row.contribution_date;
      model.expenditure_date = row.expenditure_date;
      model.contribution_amount = row.contribution_amount;
      model.expenditure_amount = row.expenditure_amount;
													
															
      model.memo_code = row.memo_code;
      model.first_name = row.first_name;
      model.last_name = row.last_name;
      model.entity_name = row.entity_name;
      model.entity_type = row.entity_type;

      modelArray.push(model);
	
    }

    console.log('91: ', modelArray);

    return modelArray;
  }

  public editTransaction(trx: any): void {
    this.scheduleAction = ScheduleActions.edit;

    trx.apiCall = '/sa/schedA';
    //trx.activityEventIdentifier = trx.activity_event_identifier;
    //trx.activityEventType = trx.activity_event_type;
    trx.backRefTransactionId = trx.back_ref_transaction_id;
    //trx.entityName = trx.entity_name;
    //trx.entityType = trx.entity_type;
    //trx.expenditureDate = trx.expenditure_date;
    //trx.fedShareAmount = trx.fed_share_amount;

    trx.transactionId = trx.transaction_id;
    trx.transactionTypeIdentifier = trx.transaction_type_identifier;

    //trx.type = 'H4';

    this._tranMessageService.sendEditTransactionMessage(trx);
  }

  
}

