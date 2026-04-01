import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RunsComponent } from './runs.component';
import { RunsService } from '../../core/services/runs.service';
import { AgUiEventService } from '../../core/services/ag-ui-event.service';
import { of, throwError } from 'rxjs';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

describe('RunsComponent', () => {
  let fixture: ComponentFixture<RunsComponent>;
  let component: RunsComponent;
  let runsServiceMock: { listRuns: ReturnType<typeof vi.fn>; startRun: ReturnType<typeof vi.fn> };
  let agUiEventServiceMock: { isBatchRunning: ReturnType<typeof signal<boolean>>; connectToBatch: ReturnType<typeof vi.fn>; filesProcessed: ReturnType<typeof signal<number>>; totalBatchFiles: ReturnType<typeof signal<number>> };

  const mockRuns = [
    {
      batch_id: 'batch-001',
      triggered_at: new Date().toISOString(),
      completed_at: null,
      total_files: 3,
      total_records: 5,
      status: 'Completed',
    },
  ];

  beforeEach(async () => {
    runsServiceMock = {
      listRuns: vi.fn().mockReturnValue(of(mockRuns)),
      startRun: vi.fn().mockReturnValue(of({ batch_id: 'new-batch', total_files: 2, status: 'In Progress' })),
    };

    agUiEventServiceMock = {
      isBatchRunning: signal(false),
      connectToBatch: vi.fn(),
      filesProcessed: signal(0),
      totalBatchFiles: signal(0),
    };

    await TestBed.configureTestingModule({
      imports: [RunsComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: RunsService, useValue: runsServiceMock },
        { provide: AgUiEventService, useValue: agUiEventServiceMock },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(RunsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display loaded runs', () => {
    expect(component.runs().length).toBe(1);
    expect(component.runs()[0].batch_id).toBe('batch-001');
  });

  it('Run Pipeline button should be disabled when isBatchRunning is true', () => {
    agUiEventServiceMock.isBatchRunning.set(true);
    fixture.detectChanges();

    const button: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    expect(button.disabled).toBe(true);
  });

  it('Run Pipeline button should be enabled when isBatchRunning is false', () => {
    agUiEventServiceMock.isBatchRunning.set(false);
    fixture.detectChanges();

    const button: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    expect(button.disabled).toBe(false);
  });

  it('startRun() should call connectToBatch with the returned batch_id', () => {
    component.startRun();
    expect(agUiEventServiceMock.connectToBatch).toHaveBeenCalledWith('new-batch');
  });

  it('should display error message when startRun fails', () => {
    runsServiceMock.startRun.mockReturnValue(throwError(() => ({ error: { detail: 'Run already in progress' } })));

    component.startRun();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('Run already in progress');
  });
});
