import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Toolkit } from './toolkit';

describe('Toolkit', () => {
  let component: Toolkit;
  let fixture: ComponentFixture<Toolkit>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Toolkit],
    }).compileComponents();

    fixture = TestBed.createComponent(Toolkit);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
