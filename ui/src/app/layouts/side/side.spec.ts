import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Side } from './side';

describe('Side', () => {
  let component: Side;
  let fixture: ComponentFixture<Side>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Side],
    }).compileComponents();

    fixture = TestBed.createComponent(Side);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
