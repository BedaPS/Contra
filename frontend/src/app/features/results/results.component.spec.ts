import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ResultsComponent } from './results.component';
import { RunsService } from '../../core/services/runs.service';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { provideHttpClient } from '@angular/common/http';
import { PaymentRecordResponse } from '../../core/models/run.models';

function makeRecord(overrides: Partial<PaymentRecordResponse> = {}): PaymentRecordResponse {
  return {
    id: 1,
    run_record_id: 'rr-001',
    batch_id: 'b-001',
    source_filename: 'invoice.pdf',
    doc_type: 'remittance',
    page_number: 1,
    customer_name: 'Test Corp',
    account_number: '****1234',
    payee: null,
    payment_id: 'TXN-1',
    payment_method: 'EFT',
    payment_date: '2024-03-15',
    invoice_number: 'INV-100',
    reference_doc_number: null,
    amount_paid: 1000.0,
    currency: 'ZAR',
    deductions: null,
    deduction_type: null,
    notes: null,
    validation_status: 'Valid',
    overall_confidence: 0.92,
    confidence_scores: { amount_paid: 0.92 },
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('ResultsComponent', () => {
  let fixture: ComponentFixture<ResultsComponent>;
  let component: ResultsComponent;
  let runsServiceMock: { getResults: ReturnType<typeof vi.fn>; listRuns: ReturnType<typeof vi.fn>; startRun: ReturnType<typeof vi.fn> };

  const allRecords: PaymentRecordResponse[] = [
    makeRecord({ id: 1, validation_status: 'Valid', doc_type: 'remittance' }),
    makeRecord({ id: 2, validation_status: 'Review Required', doc_type: 'email', source_filename: 'email.pdf' }),
    makeRecord({ id: 3, validation_status: 'Extraction Failed', doc_type: 'receipt', source_filename: 'receipt.pdf' }),
  ];

  beforeEach(async () => {
    runsServiceMock = {
      getResults: vi.fn().mockReturnValue(of(allRecords)),
      listRuns: vi.fn().mockReturnValue(of([])),
      startRun: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [ResultsComponent],
      providers: [
        provideHttpClient(),
        { provide: RunsService, useValue: runsServiceMock },
        {
          provide: ActivatedRoute,
          useValue: {
            queryParamMap: of({ get: (_key: string) => null }),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ResultsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load all records on init', () => {
    expect(component.records().length).toBe(3);
  });

  it('filter by validation_status narrows displayed rows', () => {
    runsServiceMock.getResults.mockReturnValue(of([allRecords[0]]));

    component.filterStatus = 'Valid';
    component.applyFilters();
    fixture.detectChanges();

    expect(component.records().length).toBe(1);
    expect(component.records()[0].validation_status).toBe('Valid');
  });

  it('filter by doc_type narrows displayed rows', () => {
    runsServiceMock.getResults.mockReturnValue(of([allRecords[1]]));

    component.filterDocType = 'email';
    component.applyFilters();
    fixture.detectChanges();

    expect(component.records().length).toBe(1);
    expect(component.records()[0].doc_type).toBe('email');
  });

  it('clearFilters should reset all filters and reload', () => {
    component.filterStatus = 'Valid';
    component.filterDocType = 'email';
    runsServiceMock.getResults.mockReturnValue(of(allRecords));

    component.clearFilters();

    expect(component.filterStatus).toBe('');
    expect(component.filterDocType).toBe('');
    expect(component.records().length).toBe(3);
  });

  it('toggleExpand should show/hide expanded row', () => {
    expect(component.expandedId()).toBeNull();

    component.toggleExpand(1);
    expect(component.expandedId()).toBe(1);

    component.toggleExpand(1);
    expect(component.expandedId()).toBeNull();
  });

  it('rowClass should return correct class for each validation_status', () => {
    expect(component.rowClass(allRecords[0])).toBe('row-valid');
    expect(component.rowClass(allRecords[1])).toBe('row-review');
    expect(component.rowClass(allRecords[2])).toBe('row-failed');
  });
});
